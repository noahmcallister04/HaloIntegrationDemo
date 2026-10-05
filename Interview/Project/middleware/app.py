"""Similar Resolved Tickets middleware.

Halo webhooks in, private notes out, plus a Similar Tickets page that a Halo ticket Custom
Button opens in a new window (/similar?ticket_id=$FAULTID).
"""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from middleware.halo_client import Ticket
from middleware.matcher import Match, SearchResult
from middleware.notes import ticket_link
from middleware.service import SimilarTicketsService
from settings import load_config

STATIC = Path(__file__).parent / "static"
cfg = load_config()
service = SimilarTicketsService(cfg)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(service.start)
    yield
    service.close()


app = FastAPI(title="Similar Resolved Tickets", lifespan=lifespan)


class FeedbackIn(BaseModel):
    suggested_ticket_id: int
    helpful: bool
    open_ticket_id: int | None = None


def check_webhook_secret(secret: str | None) -> None:
    expected = cfg["middleware"]["webhook_secret"]
    if not secret or not secrets.compare_digest(secret, expected):
        raise HTTPException(401, "Invalid webhook secret")


def webhook_ticket_id(payload: dict) -> int:
    # Only the id is trusted from the payload; the ticket is re-fetched from the Halo API.
    raw = payload.get("ticket_id") or payload.get("id") or (payload.get("ticket") or {}).get("id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise HTTPException(422, "Webhook payload has no ticket id")


@app.post("/webhooks/ticket-created", status_code=202)
def ticket_created(
    background: BackgroundTasks,
    payload: dict = Body(...),
    x_webhook_secret: str | None = Header(None),
):
    check_webhook_secret(x_webhook_secret)
    ticket_id = webhook_ticket_id(payload)
    background.add_task(service.handle_ticket_created, ticket_id)
    return {"accepted": True, "ticket_id": ticket_id}


@app.post("/webhooks/ticket-closed", status_code=202)
def ticket_closed(
    background: BackgroundTasks,
    payload: dict = Body(...),
    x_webhook_secret: str | None = Header(None),
):
    check_webhook_secret(x_webhook_secret)
    ticket_id = webhook_ticket_id(payload)
    background.add_task(service.handle_ticket_closed, ticket_id)
    return {"accepted": True, "ticket_id": ticket_id}


def match_json(m: Match, threshold: float) -> dict:
    t = m.ticket
    return {
        "ticket_id": t.id,
        "url": ticket_link(t.id, cfg["halo"]["ticket_url"]),
        "score": m.score,
        "semantic": m.semantic,
        "boosts": m.boosts,
        "matched_concepts": m.matched_concepts,
        "above_threshold": m.score >= threshold,
        "weak_resolution": m.weak_resolution,
        "client": t.client,
        "site": t.site,
        "type": t.type,
        "subtype": t.subtype,
        "asset_model": t.asset_model,
        "summary": t.summary,
        "resolution": t.resolution,
        "date_closed": t.date_closed,
    }


def result_json(result: SearchResult, query: dict) -> dict:
    return {
        "query": query,
        "normalized_text": result.normalized_text,
        "concepts": result.concepts,
        "threshold": result.threshold,
        "confident": result.confident,
        "hidden_no_resolution": result.hidden_no_resolution,
        "results": [match_json(m, result.threshold) for m in result.matches],
    }


def ticket_json(t: Ticket) -> dict:
    return {
        "ticket_id": t.id, "summary": t.summary, "client": t.client, "site": t.site,
        "type": t.type, "subtype": t.subtype, "asset_model": t.asset_model, "status": t.status,
    }


@app.get("/api/similar")
def similar(
    ticket_id: int | None = None,
    q: str | None = None,
    limit: int = Query(cfg["matching"]["top_k_lookup"], ge=1, le=20),
):
    if ticket_id is not None:
        try:
            ticket, result = service.search_ticket(ticket_id, limit)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(404, f"Ticket #{ticket_id} not found in Halo")
            raise HTTPException(502, f"Halo API error: {exc.response.status_code}")
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"Could not reach Halo: {exc}")
        return result_json(result, ticket_json(ticket))
    if q and q.strip():
        return result_json(service.search_text(q, limit), {"text": q})
    raise HTTPException(422, "Provide ticket_id or q")


@app.post("/api/feedback")
def feedback(body: FeedbackIn):
    service.record_feedback(body.open_ticket_id, body.suggested_ticket_id, body.helpful)
    return {"ok": True}


@app.get("/api/stats")
def stats():
    return service.stats()


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True, "indexed_tickets": len(service.index)}


# The page opens in its own window, so nothing needs to frame it (and feedback buttons can't be clickjacked).
PAGE_HEADERS = {"Content-Security-Policy": "frame-ancestors 'none'"}


@app.get("/similar", include_in_schema=False)
def similar_page():
    return FileResponse(STATIC / "similar.html", headers=PAGE_HEADERS)


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "Similar Resolved Tickets",
        "halo_custom_button_url": f"{cfg['middleware']['public_url'].rstrip('/')}/similar?ticket_id=$FAULTID",
    }
