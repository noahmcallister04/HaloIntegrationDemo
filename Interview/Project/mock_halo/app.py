"""Mock HaloPSA instance.

Exposes the same kind of REST resources as Halo (/auth/token, /api/Tickets, /api/Actions)
so the middleware's HaloClient can later be pointed at a real instance by changing config.
It also fires webhooks on ticket create/close and serves a small ticket UI for the demo.
"""
from __future__ import annotations

import logging
import secrets
import time
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Form, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from mock_halo import db
from mock_halo.reference import AGENTS, CLIENTS, IMPACTS, TYPES, URGENCIES
from settings import load_config

log = logging.getLogger("uvicorn.error")
cfg = load_config()
STATIC = Path(__file__).parent / "static"
TOKEN_TTL_SECONDS = 3600

app = FastAPI(title="Mock Halo")
db.init_db()

_tokens: dict[str, float] = {}


class TicketIn(BaseModel):
    summary: str
    details: str = ""
    client_name: str | None = None
    site_name: str | None = None
    user_name: str | None = None
    type: str | None = None
    subtype: str | None = None
    impact: int = 3
    urgency: int = 2
    team: str | None = None
    agent: str | None = None
    additional_agent: str | None = None
    asset_model: str | None = None
    channel: str | None = None


class ActionIn(BaseModel):
    ticket_id: int
    note: str
    note_html: str | None = None
    outcome: str = "Private Note"
    hiddenfromuser: bool = True
    who: str | None = None


class CloseIn(BaseModel):
    resolution: str
    agent: str | None = None


# --- Auth ----------------------------------------------------------------------------------

@app.post("/auth/token")
def issue_token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: str = Form("all"),
):
    if grant_type != "client_credentials":
        raise HTTPException(400, {"error": "unsupported_grant_type"})
    expected = cfg["mock_halo"]
    if not (
        secrets.compare_digest(client_id, expected["client_id"])
        and secrets.compare_digest(client_secret, expected["client_secret"])
    ):
        raise HTTPException(401, {"error": "invalid_client"})
    token = secrets.token_urlsafe(32)
    _tokens[token] = time.time() + TOKEN_TTL_SECONDS
    return {"access_token": token, "token_type": "Bearer", "expires_in": TOKEN_TTL_SECONDS, "scope": scope}


def require_token(authorization: str | None = Header(None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    expiry = _tokens.get(authorization.removeprefix("Bearer "))
    if not expiry or expiry < time.time():
        raise HTTPException(401, "Invalid or expired token")


# --- Webhooks ------------------------------------------------------------------------------

def fire_webhook(event: str, ticket_id: int) -> None:
    url = cfg["mock_halo"]["webhooks"].get(event)
    if not url:
        return
    with db.connect() as conn:
        ticket = db.get_ticket(conn, ticket_id)
    payload = {"event": event, "ticket_id": ticket_id, "ticket": ticket}
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"X-Webhook-Secret": cfg["middleware"]["webhook_secret"]},
            timeout=10,
        )
        log.info("webhook %s for ticket %s -> %s", event, ticket_id, resp.status_code)
    except httpx.HTTPError as exc:
        log.warning("webhook %s for ticket %s failed: %s", event, ticket_id, exc)


def _create(tickets: list[TicketIn], background: BackgroundTasks) -> list[dict]:
    with db.connect() as conn:
        created = [db.create_ticket(conn, t.model_dump()) for t in tickets]
    for t in created:
        background.add_task(fire_webhook, "ticket_created", t["id"])
    return created


def _close(ticket_id: int, body: CloseIn, background: BackgroundTasks) -> dict:
    if not body.resolution.strip():
        raise HTTPException(422, "Resolution is required to close a ticket")
    with db.connect() as conn:
        ticket = db.get_ticket(conn, ticket_id)
        if not ticket:
            raise HTTPException(404, "Ticket not found")
        if ticket["status"] == db.CLOSED_STATUS:
            raise HTTPException(409, "Ticket is already closed")
        closed = db.close_ticket(conn, ticket_id, body.resolution.strip(), body.agent)
    background.add_task(fire_webhook, "ticket_closed", ticket_id)
    return closed


# --- Halo-style API (bearer token required) -------------------------------------------------

api = [Depends(require_token)]


@app.get("/api/Tickets", dependencies=api)
def api_list_tickets(
    closed_only: bool = False,
    open_only: bool = False,
    search: str | None = None,
    page_size: int = Query(50, ge=1, le=500),
    page_no: int = Query(1, ge=1),
):
    with db.connect() as conn:
        tickets, total = db.list_tickets(
            conn, closed_only=closed_only, open_only=open_only, search=search,
            page_size=page_size, page_no=page_no,
        )
    return {"page_no": page_no, "page_size": page_size, "record_count": total, "tickets": tickets}


@app.get("/api/Tickets/{ticket_id}", dependencies=api)
def api_get_ticket(ticket_id: int):
    with db.connect() as conn:
        ticket = db.get_ticket(conn, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return ticket


@app.post("/api/Tickets", dependencies=api)
def api_create_tickets(body: TicketIn | list[TicketIn], background: BackgroundTasks):
    # Halo's POST endpoints accept an array; accept a single object too.
    created = _create(body if isinstance(body, list) else [body], background)
    return created if isinstance(body, list) else created[0]


@app.post("/api/Tickets/{ticket_id}/close", dependencies=api)
def api_close_ticket(ticket_id: int, body: CloseIn, background: BackgroundTasks):
    return _close(ticket_id, body, background)


@app.get("/api/Actions", dependencies=api)
def api_list_actions(ticket_id: int):
    with db.connect() as conn:
        actions = db.list_actions(conn, ticket_id)
    return {"record_count": len(actions), "actions": actions}


@app.post("/api/Actions", dependencies=api)
def api_add_actions(body: ActionIn | list[ActionIn]):
    items = body if isinstance(body, list) else [body]
    with db.connect() as conn:
        for a in items:
            if not db.get_ticket(conn, a.ticket_id):
                raise HTTPException(404, f"Ticket {a.ticket_id} not found")
        created = [
            db.add_action(conn, a.ticket_id, a.note, a.outcome, a.hiddenfromuser, a.who, a.note_html)
            for a in items
        ]
    return created if isinstance(body, list) else created[0]


# --- Demo UI (mock only, no auth) -----------------------------------------------------------

@app.get("/", include_in_schema=False)
def ui_page():
    return FileResponse(STATIC / "index.html")


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}


@app.get("/ui/meta", include_in_schema=False)
def ui_meta():
    return {
        "clients": {name: c["sites"] for name, c in CLIENTS.items()},
        "types": TYPES,
        "impacts": IMPACTS,
        "urgencies": URGENCIES,
        "agents": AGENTS,
        "custom_buttons": cfg["mock_halo"].get("custom_buttons", []),
    }


@app.get("/ui/tickets", include_in_schema=False)
def ui_list_tickets(status: str = "open", search: str | None = None):
    with db.connect() as conn:
        tickets, total = db.list_tickets(
            conn, closed_only=status == "closed", open_only=status == "open",
            search=search, page_size=200,
        )
    return {"record_count": total, "tickets": tickets}


@app.get("/ui/tickets/{ticket_id}", include_in_schema=False)
def ui_get_ticket(ticket_id: int):
    with db.connect() as conn:
        ticket = db.get_ticket(conn, ticket_id)
        if not ticket:
            raise HTTPException(404, "Ticket not found")
        ticket["actions"] = db.list_actions(conn, ticket_id)
    return ticket


@app.post("/ui/tickets", include_in_schema=False)
def ui_create_ticket(body: TicketIn, background: BackgroundTasks):
    return _create([body], background)[0]


class UiActionIn(BaseModel):
    note: str
    outcome: str = "Private Note"
    hiddenfromuser: bool = True
    who: str | None = None


@app.post("/ui/tickets/{ticket_id}/actions", include_in_schema=False)
def ui_add_action(ticket_id: int, body: UiActionIn):
    if not body.note.strip():
        raise HTTPException(422, "Note is required")
    with db.connect() as conn:
        if not db.get_ticket(conn, ticket_id):
            raise HTTPException(404, "Ticket not found")
        return db.add_action(conn, ticket_id, body.note.strip(), body.outcome, body.hiddenfromuser, body.who)


@app.post("/ui/tickets/{ticket_id}/close", include_in_schema=False)
def ui_close_ticket(ticket_id: int, body: CloseIn, background: BackgroundTasks):
    return _close(ticket_id, body, background)
