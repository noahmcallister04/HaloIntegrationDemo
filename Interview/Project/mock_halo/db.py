"""SQLite storage for the mock Halo instance."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from settings import load_config, resolve_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id                INTEGER PRIMARY KEY,
    summary           TEXT NOT NULL,
    details           TEXT NOT NULL DEFAULT '',
    client_name       TEXT,
    site_name         TEXT,
    user_name         TEXT,
    type              TEXT,
    subtype           TEXT,
    impact            INTEGER,
    urgency           INTEGER,
    priority          TEXT,
    status            TEXT NOT NULL,
    team              TEXT,
    agent             TEXT,
    additional_agent  TEXT,
    asset_model       TEXT,
    date_reported     TEXT NOT NULL,
    last_action_date  TEXT,
    resolution_target TEXT,
    sla_action_date   TEXT,
    time_taken        REAL NOT NULL DEFAULT 0,
    date_closed       TEXT,
    channel           TEXT
);
CREATE TABLE IF NOT EXISTS actions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id      INTEGER NOT NULL REFERENCES tickets(id),
    note           TEXT NOT NULL,
    note_html      TEXT,
    outcome        TEXT NOT NULL,
    hiddenfromuser INTEGER NOT NULL DEFAULT 0,
    who            TEXT,
    datetime       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_ticket ON actions(ticket_id);
"""

# Impact (1 Company .. 3 Single User) x Urgency (1 High .. 3 Low) -> priority.
# Assumes a standard ITIL matrix; confirm against FeatherShark's Halo priority setup.
PRIORITY_MATRIX = {
    (1, 1): 1, (1, 2): 2, (1, 3): 3,
    (2, 1): 2, (2, 2): 3, (2, 3): 3,
    (3, 1): 3, (3, 2): 3, (3, 3): 4,
}
# priority -> (response hours, resolution hours)
SLA_HOURS = {1: (0.25, 4), 2: (1, 8), 3: (4, 24), 4: (8, 72)}

CLOSED_STATUS = "Closed"


def db_path() -> Path:
    return resolve_path(load_config()["mock_halo"]["db_path"])


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        # Databases seeded before the channel column existed.
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(tickets)")}
        if "channel" not in columns:
            conn.execute("ALTER TABLE tickets ADD COLUMN channel TEXT")
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(actions)")}
        if "note_html" not in columns:
            conn.execute("ALTER TABLE actions ADD COLUMN note_html TEXT")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def priority_for(impact: int, urgency: int) -> int:
    return PRIORITY_MATRIX.get((impact, urgency), 3)


def sla_dates(reported: datetime, priority: int) -> tuple[str, str]:
    response_h, resolution_h = SLA_HOURS[priority]
    return (
        (reported + timedelta(hours=resolution_h)).isoformat(timespec="seconds"),
        (reported + timedelta(hours=response_h)).isoformat(timespec="seconds"),
    )


def ticket_to_json(row: sqlite3.Row) -> dict:
    t = dict(row)
    t["sla_time_left_hours"] = None
    if t["status"] != CLOSED_STATUS and t["resolution_target"]:
        left = datetime.fromisoformat(t["resolution_target"]) - datetime.now()
        t["sla_time_left_hours"] = round(left.total_seconds() / 3600, 1)
    return t


def get_ticket(conn: sqlite3.Connection, ticket_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return ticket_to_json(row) if row else None


def list_tickets(
    conn: sqlite3.Connection,
    *,
    closed_only: bool = False,
    open_only: bool = False,
    search: str | None = None,
    page_size: int = 50,
    page_no: int = 1,
) -> tuple[list[dict], int]:
    where, params = [], []
    if closed_only:
        where.append("status = ?")
        params.append(CLOSED_STATUS)
    elif open_only:
        where.append("status != ?")
        params.append(CLOSED_STATUS)
    if search:
        where.append("(summary LIKE ? OR details LIKE ? OR CAST(id AS TEXT) = ?)")
        params += [f"%{search}%", f"%{search}%", search.strip().lstrip("#")]
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM tickets {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM tickets {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [page_size, (page_no - 1) * page_size],
    ).fetchall()
    return [ticket_to_json(r) for r in rows], total


def create_ticket(conn: sqlite3.Connection, data: dict) -> dict:
    reported = datetime.now()
    impact, urgency = int(data.get("impact") or 3), int(data.get("urgency") or 2)
    priority = priority_for(impact, urgency)
    resolution_target, sla_action = sla_dates(reported, priority)
    cur = conn.execute(
        """INSERT INTO tickets (summary, details, client_name, site_name, user_name, type, subtype,
               impact, urgency, priority, status, team, agent, additional_agent, asset_model,
               date_reported, last_action_date, resolution_target, sla_action_date, channel)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["summary"], data.get("details") or "", data.get("client_name"),
            data.get("site_name"), data.get("user_name"), data.get("type"), data.get("subtype"),
            impact, urgency, f"P{priority}", data.get("team") or "Service Desk",
            data.get("agent"), data.get("additional_agent"), data.get("asset_model"),
            reported.isoformat(timespec="seconds"), reported.isoformat(timespec="seconds"),
            resolution_target, sla_action, data.get("channel") or "Manual",
        ),
    )
    return get_ticket(conn, cur.lastrowid)


def add_action(
    conn: sqlite3.Connection,
    ticket_id: int,
    note: str,
    outcome: str,
    hiddenfromuser: bool,
    who: str | None,
    note_html: str | None = None,
) -> dict:
    stamp = now_iso()
    cur = conn.execute(
        """INSERT INTO actions (ticket_id, note, note_html, outcome, hiddenfromuser, who, datetime)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ticket_id, note, note_html, outcome, int(hiddenfromuser), who, stamp),
    )
    conn.execute("UPDATE tickets SET last_action_date = ? WHERE id = ?", (stamp, ticket_id))
    return action_to_json(conn.execute("SELECT * FROM actions WHERE id = ?", (cur.lastrowid,)).fetchone())


def close_ticket(conn: sqlite3.Connection, ticket_id: int, resolution: str, agent: str | None) -> dict:
    """Closes a ticket. The fix is stored as the closing action's note (outcome "Resolved")."""
    stamp = now_iso()
    conn.execute(
        "UPDATE tickets SET status = ?, date_closed = ?, agent = COALESCE(?, agent) WHERE id = ?",
        (CLOSED_STATUS, stamp, agent, ticket_id),
    )
    add_action(conn, ticket_id, resolution, "Resolved", False, agent)
    return get_ticket(conn, ticket_id)


def action_to_json(row: sqlite3.Row) -> dict:
    a = dict(row)
    a["hiddenfromuser"] = bool(a["hiddenfromuser"])
    return a


def list_actions(conn: sqlite3.Connection, ticket_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM actions WHERE ticket_id = ? ORDER BY datetime, id", (ticket_id,)
    ).fetchall()
    return [action_to_json(r) for r in rows]
