"""Finds similar closed tickets: semantic similarity, re-ranked with structured boosts."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import numpy as np

from middleware.halo_client import Ticket
from middleware.indexer import Embedder, IndexedTicket, TicketIndex, problem_text
from middleware.preprocess import Normalizer

GENERIC_RESOLUTIONS = {
    "fixed", "done", "resolved", "working now", "works now", "complete", "completed", "n/a", "na",
    "see notes", "see above", "user fixed it", "closed", "rebooted", "ok",
}


@dataclass
class Match:
    ticket: IndexedTicket
    score: float  # clipped to 0..1 for display and thresholds
    semantic: float
    boosts: dict[str, float]
    matched_concepts: list[str]
    weak_resolution: bool
    raw_score: float  # unclipped, used for ranking so near-duplicates don't tie at 1.0


@dataclass
class SearchResult:
    normalized_text: str
    concepts: list[str]
    matches: list[Match]
    threshold: float
    # Close semantic matches skipped because the ticket was closed without resolution notes.
    hidden_no_resolution: int = 0
    excluded_ids: set[int] = field(default_factory=set)

    @property
    def confident(self) -> bool:
        """True when the best match with real fix notes clears the posting threshold."""
        best = next((m for m in self.matches if not m.weak_resolution), None)
        return best is not None and best.score >= self.threshold


def is_weak_resolution(resolution: str | None, min_length: int) -> bool:
    text = (resolution or "").strip()
    return len(text) < min_length or text.lower().rstrip(".!") in GENERIC_RESOLUTIONS


def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


class Matcher:
    def __init__(
        self,
        index: TicketIndex,
        normalizer: Normalizer,
        embedder: Embedder,
        matching_cfg: dict,
        feedback_scores: Callable[[], dict[int, int]] = dict,
    ):
        self.index = index
        self.normalizer = normalizer
        self.embedder = embedder
        self.cfg = matching_cfg
        self.weights = matching_cfg["weights"]
        self.feedback_scores = feedback_scores

    @property
    def threshold(self) -> float:
        return float(self.cfg["post_threshold"])

    def search(
        self,
        *,
        query: Ticket | None = None,
        text: str | None = None,
        top_k: int = 3,
        exclude_ids: set[int] | None = None,
        now: datetime | None = None,
    ) -> SearchResult:
        if query is None and not text:
            raise ValueError("search needs a ticket or text")
        exclude = set(exclude_ids or ())
        if query is not None:
            exclude.add(query.id)
        processed = self.normalizer.process(problem_text(query) if query else text)
        result = SearchResult(
            normalized_text=processed.normalized_text,
            concepts=sorted(processed.concepts),
            matches=[],
            threshold=self.threshold,
            excluded_ids=exclude,
        )
        snap = self.index.snapshot()
        if not len(snap.ids) or not processed.normalized_text:
            return result

        qvec = self.embedder.encode([processed.normalized_text])[0]
        # Best of "looks like the problem" and "looks like the problem + its fix".
        semantic = np.maximum(snap.problem @ qvec, snap.full @ qvec)
        pool = np.argsort(-semantic)[: int(self.cfg.get("candidate_pool", 50))]

        feedback = self.feedback_scores()
        now = now or datetime.now()
        min_length = int(self.cfg["resolution"]["min_length"])
        min_score = float(self.cfg["min_result_score"])
        matches: list[Match] = []
        for i in pool:
            tid = int(snap.ids[i])
            if tid in exclude:
                continue
            ticket = snap.tickets[tid]
            sem = float(semantic[i])
            if not (ticket.resolution or "").strip():
                if sem >= min_score:
                    result.hidden_no_resolution += 1
                continue
            weak = is_weak_resolution(ticket.resolution, min_length)
            boosts = self._boosts(query, processed.concepts, ticket, now, feedback.get(tid, 0), weak)
            raw = sem + sum(boosts.values())
            matches.append(Match(
                ticket=ticket,
                score=round(min(1.0, max(0.0, raw)), 4),
                semantic=round(sem, 4),
                boosts=boosts,
                matched_concepts=sorted(processed.concepts & ticket.concepts),
                weak_resolution=weak,
                raw_score=raw,
            ))
        matches.sort(key=lambda m: m.raw_score, reverse=True)
        result.matches = matches[:top_k]
        return result

    def _boosts(
        self,
        query: Ticket | None,
        query_concepts: set[str],
        t: IndexedTicket,
        now: datetime,
        net_votes: int,
        weak_resolution: bool,
    ) -> dict[str, float]:
        w = self.weights
        boosts: dict[str, float] = {}
        if query is not None:
            if _same(query.client, t.client):
                boosts["same_client"] = w["same_client"]
                if _same(query.site, t.site):
                    boosts["same_site"] = w["same_site"]
            if _same(query.type, t.type):
                boosts["same_type"] = w["same_type"]
                if _same(query.subtype, t.subtype):
                    boosts["same_subtype"] = w["same_subtype"]
            if _same(query.asset_model, t.asset_model):
                boosts["same_asset_model"] = w["same_asset_model"]
        union = query_concepts | t.concepts
        shared = query_concepts & t.concepts
        if shared:
            boosts["shared_concepts"] = w["shared_concepts"] * len(shared) / len(union)
        if t.date_closed:
            age_days = max(0.0, (now - datetime.fromisoformat(t.date_closed)).total_seconds() / 86400)
            boosts["recency"] = w["recency"] * math.pow(0.5, age_days / w["recency_half_life_days"])
        if net_votes:
            cap = w["feedback_cap"]
            boosts["feedback"] = max(-cap, min(cap, net_votes * w["feedback_step"]))
        if weak_resolution:
            boosts["weak_resolution"] = -float(self.cfg["resolution"]["weak_penalty"])
        return {k: round(v, 4) for k, v in boosts.items()}
