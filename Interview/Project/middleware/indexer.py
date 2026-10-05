"""Embeds closed tickets and keeps the in-memory similarity index in sync with SQLite.

At MSP scale (thousands of tickets) a NumPy matrix in memory is plenty; no vector DB needed.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from middleware import db
from middleware.halo_client import HaloClient, Ticket
from middleware.preprocess import Normalizer

log = logging.getLogger(__name__)


class Embedder(Protocol):
    model_name: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class SentenceEmbedder:
    """sentence-transformers model, loaded lazily. Runs on CPU, no API key."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                log.info("Loading embedding model %s", self.model_name)
                self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        if not texts:
            return np.zeros((0, model.get_sentence_embedding_dimension()), dtype=np.float32)
        vectors = model.encode(
            texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        return vectors.astype(np.float32)


@dataclass(frozen=True)
class IndexedTicket:
    id: int
    client: str | None
    site: str | None
    type: str | None
    subtype: str | None
    asset_model: str | None
    summary: str
    resolution: str | None
    concepts: frozenset[str]
    date_closed: str | None


@dataclass(frozen=True)
class IndexSnapshot:
    ids: np.ndarray       # (n,)
    problem: np.ndarray   # (n, d) unit vectors of summary + details
    full: np.ndarray      # (n, d) unit vectors of summary + details + resolution
    tickets: dict[int, IndexedTicket]


def problem_text(ticket: Ticket) -> str:
    return f"{ticket.summary}\n{ticket.details}"


class TicketIndex:
    def __init__(self, db_path: Path, embedder: Embedder, normalizer: Normalizer):
        self.db_path = db_path
        self.embedder = embedder
        self.normalizer = normalizer
        self._lock = threading.Lock()
        self._snapshot = IndexSnapshot(
            np.zeros(0, dtype=np.int64), np.zeros((0, 0), np.float32), np.zeros((0, 0), np.float32), {}
        )
        db.init_db(db_path)

    def __len__(self) -> int:
        return len(self._snapshot.ids)

    def __contains__(self, ticket_id: int) -> bool:
        return ticket_id in self._snapshot.tickets

    def snapshot(self) -> IndexSnapshot:
        return self._snapshot

    def load(self) -> None:
        """Reads the index into memory. Vectors from a different model are ignored (re-embedded on sync)."""
        with db.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT t.*, e.problem_vector, e.full_vector FROM indexed_tickets t
                   JOIN embeddings e ON e.ticket_id = t.id WHERE e.model = ? ORDER BY t.id""",
                (self.embedder.model_name,),
            ).fetchall()
        tickets: dict[int, IndexedTicket] = {}
        problem, full = [], []
        for r in rows:
            tickets[r["id"]] = IndexedTicket(
                id=r["id"], client=r["client"], site=r["site"], type=r["type"], subtype=r["subtype"],
                asset_model=r["asset_model"], summary=r["summary"], resolution=r["resolution"],
                concepts=frozenset(json.loads(r["concepts"] or "[]")), date_closed=r["date_closed"],
            )
            problem.append(np.frombuffer(r["problem_vector"], dtype=np.float32))
            full.append(np.frombuffer(r["full_vector"], dtype=np.float32))
        snapshot = IndexSnapshot(
            ids=np.array(list(tickets), dtype=np.int64),
            problem=np.vstack(problem) if problem else np.zeros((0, 0), np.float32),
            full=np.vstack(full) if full else np.zeros((0, 0), np.float32),
            tickets=tickets,
        )
        with self._lock:
            self._snapshot = snapshot

    def upsert(self, tickets: list[Ticket]) -> int:
        """Embeds closed tickets and adds/replaces them in the index."""
        tickets = [t for t in tickets if t.is_closed]
        if not tickets:
            return 0
        problems = [self.normalizer.process(problem_text(t)) for t in tickets]
        fixes = [self.normalizer.process(t.resolution or "") for t in tickets]
        full_texts = [
            f"{p.normalized_text} fix: {f.normalized_text}".strip() for p, f in zip(problems, fixes)
        ]
        problem_vecs = self.embedder.encode([p.normalized_text for p in problems])
        full_vecs = self.embedder.encode(full_texts)
        stamp = db.now_iso()
        with db.connect(self.db_path) as conn:
            for t, p, pv, fv in zip(tickets, problems, problem_vecs, full_vecs):
                conn.execute(
                    """INSERT OR REPLACE INTO indexed_tickets
                       (id, client, site, type, subtype, asset_model, summary, details, resolution,
                        normalized_text, concepts, date_reported, date_closed, indexed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (t.id, t.client, t.site, t.type, t.subtype, t.asset_model, t.summary, t.details,
                     t.resolution, p.normalized_text, json.dumps(sorted(p.concepts)), t.date_reported,
                     t.date_closed, stamp),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO embeddings (ticket_id, problem_vector, full_vector, model) VALUES (?, ?, ?, ?)",
                    (t.id, pv.tobytes(), fv.tobytes(), self.embedder.model_name),
                )
        # Reloading the whole index is a few ms at this scale and keeps one code path.
        self.load()
        return len(tickets)

    def sync_from_halo(self, halo: HaloClient) -> int:
        """Backfills closed tickets missing from the index (first run, or webhooks missed while down)."""
        missing = [t for t in halo.iter_closed_tickets() if t.id not in self]
        if not missing:
            return 0
        log.info("Backfilling %d closed tickets from Halo", len(missing))
        for t in missing:
            t.resolution = halo.get_resolution(t.id)
        return self.upsert(missing)
