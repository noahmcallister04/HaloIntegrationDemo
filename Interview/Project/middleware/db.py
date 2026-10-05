"""SQLite storage for the middleware: the closed-ticket index, posted suggestions, feedback."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS indexed_tickets (
    id              INTEGER PRIMARY KEY,
    client          TEXT,
    site            TEXT,
    type            TEXT,
    subtype         TEXT,
    asset_model     TEXT,
    summary         TEXT,
    details         TEXT,
    resolution      TEXT,
    normalized_text TEXT,
    concepts        TEXT,
    date_reported   TEXT,
    date_closed     TEXT,
    indexed_at      TEXT NOT NULL
);
-- Two vectors per ticket: the problem alone, and problem + fix.
CREATE TABLE IF NOT EXISTS embeddings (
    ticket_id      INTEGER PRIMARY KEY REFERENCES indexed_tickets(id),
    problem_vector BLOB NOT NULL,
    full_vector    BLOB NOT NULL,
    model          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suggestions (
    open_ticket_id INTEGER PRIMARY KEY,
    top_ticket_id  INTEGER,
    top_score      REAL,
    posted         INTEGER NOT NULL,
    note_action_id INTEGER,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    open_ticket_id      INTEGER,
    suggested_ticket_id INTEGER NOT NULL,
    helpful             INTEGER NOT NULL,
    created_at          TEXT NOT NULL
);
"""


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(path: Path) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
