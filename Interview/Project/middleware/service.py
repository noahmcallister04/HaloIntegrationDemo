"""Wires Halo, the index and the matcher together. The FastAPI app stays a thin layer over this."""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from middleware import db
from middleware.halo_client import HaloClient, Ticket
from middleware.indexer import SentenceEmbedder, TicketIndex
from middleware.matcher import Matcher, SearchResult
from middleware.notes import format_private_note, format_private_note_html, select_for_note
from middleware.preprocess import Normalizer
from settings import resolve_path

log = logging.getLogger("uvicorn.error")


class SimilarTicketsService:
    def __init__(self, cfg: dict, halo: HaloClient | None = None, embedder=None):
        self.cfg = cfg
        self.db_path: Path = resolve_path(cfg["middleware"]["db_path"])
        self.halo = halo or HaloClient.from_config(cfg)
        pre = cfg["preprocess"]
        self.normalizer = Normalizer.from_file(resolve_path(pre["synonyms_path"]), pre["fuzzy_threshold"])
        self.embedder = embedder or SentenceEmbedder(cfg["matching"]["model"])
        self.index = TicketIndex(self.db_path, self.embedder, self.normalizer)
        self.matcher = Matcher(self.index, self.normalizer, self.embedder, cfg["matching"], self.feedback_scores)

    # --- startup ---------------------------------------------------------------------------

    def start(self) -> None:
        self.index.load()
        log.info("Index loaded: %d closed tickets", len(self.index))
        try:
            added = self.index.sync_from_halo(self.halo)
            log.info("Synced with Halo: %d new closed tickets indexed (total %d)", added, len(self.index))
        except httpx.HTTPError as exc:
            log.warning("Could not sync with Halo at startup (%s); using existing index", exc)
        # Warm the model so the first webhook isn't slow.
        self.embedder.encode(["warm up"])

    # --- webhooks --------------------------------------------------------------------------

    def handle_ticket_created(self, ticket_id: int) -> None:
        try:
            with db.connect(self.db_path) as conn:
                done = conn.execute(
                    "SELECT 1 FROM suggestions WHERE open_ticket_id = ?", (ticket_id,)
                ).fetchone()
            if done:
                log.info("Ticket %s already processed, skipping duplicate webhook", ticket_id)
                return
            ticket = self.halo.get_ticket(ticket_id)
            m = self.cfg["matching"]
            top_k = int(m["top_k_note"])
            # Search a little wider so weak-resolution matches can be dropped without leaving gaps.
            result = self.matcher.search(query=ticket, top_k=top_k + 5)
            to_post = select_for_note(result, top_k, float(m["min_result_score"]))
            top = to_post[0] if to_post else (result.matches[0] if result.matches else None)
            action_id = None
            if to_post:
                action_id = self.halo.add_private_note(
                    ticket_id,
                    format_private_note(to_post),
                    format_private_note_html(to_post, self.cfg["halo"]["ticket_url"]),
                    self.cfg["middleware"].get("note_author"),
                )
                log.info("Ticket %s: posted note, top match #%s (%.2f)", ticket_id, top.ticket.id, top.score)
            else:
                log.info(
                    "Ticket %s: no note, best usable score %.2f below threshold %.2f",
                    ticket_id, top.score if top else 0.0, result.threshold,
                )
            with db.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO suggestions VALUES (?, ?, ?, ?, ?, ?)",
                    (ticket_id, top.ticket.id if top else None, top.score if top else None,
                     int(action_id is not None), action_id, db.now_iso()),
                )
        except Exception:
            log.exception("Failed to process ticket-created for ticket %s", ticket_id)

    def handle_ticket_closed(self, ticket_id: int) -> None:
        try:
            ticket = self.halo.get_closed_ticket(ticket_id)
            if self.index.upsert([ticket]):
                log.info("Ticket %s closed: added to index (total %d)", ticket_id, len(self.index))
        except Exception:
            log.exception("Failed to index closed ticket %s", ticket_id)

    # --- search (Similar Tickets tab) --------------------------------------------------------

    def search_ticket(self, ticket_id: int, top_k: int) -> tuple[Ticket, SearchResult]:
        ticket = self.halo.get_ticket(ticket_id)
        return ticket, self.matcher.search(query=ticket, top_k=top_k)

    def search_text(self, text: str, top_k: int) -> SearchResult:
        return self.matcher.search(text=text, top_k=top_k)

    # --- feedback --------------------------------------------------------------------------

    def feedback_scores(self) -> dict[int, int]:
        """Net helpful votes per suggested ticket (helpful = +1, not helpful = -1)."""
        with db.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT suggested_ticket_id, SUM(CASE WHEN helpful = 1 THEN 1 ELSE -1 END) AS net
                   FROM feedback GROUP BY suggested_ticket_id"""
            ).fetchall()
        return {r["suggested_ticket_id"]: r["net"] for r in rows}

    def record_feedback(self, open_ticket_id: int | None, suggested_ticket_id: int, helpful: bool) -> None:
        with db.connect(self.db_path) as conn:
            if open_ticket_id is not None:
                # One vote per technician-facing suggestion; changing your mind replaces it.
                conn.execute(
                    "DELETE FROM feedback WHERE open_ticket_id = ? AND suggested_ticket_id = ?",
                    (open_ticket_id, suggested_ticket_id),
                )
            conn.execute(
                "INSERT INTO feedback (open_ticket_id, suggested_ticket_id, helpful, created_at) VALUES (?, ?, ?, ?)",
                (open_ticket_id, suggested_ticket_id, int(helpful), db.now_iso()),
            )

    def stats(self) -> dict:
        with db.connect(self.db_path) as conn:
            s = conn.execute(
                "SELECT COUNT(*) AS processed, COALESCE(SUM(posted), 0) AS posted FROM suggestions"
            ).fetchone()
            f = conn.execute(
                "SELECT COUNT(*) AS votes, COALESCE(SUM(helpful), 0) AS helpful FROM feedback"
            ).fetchone()
        return {
            "indexed_tickets": len(self.index),
            "tickets_processed": s["processed"],
            "notes_posted": s["posted"],
            "feedback_votes": f["votes"],
            "helpful_votes": f["helpful"],
            "helpful_rate": round(f["helpful"] / f["votes"], 3) if f["votes"] else None,
        }

    def close(self) -> None:
        self.halo.close()
