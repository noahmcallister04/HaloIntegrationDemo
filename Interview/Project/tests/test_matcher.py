import hashlib
import re
from datetime import datetime

import numpy as np
import pytest

from middleware.halo_client import Ticket
from middleware.indexer import TicketIndex
from middleware.matcher import Matcher, is_weak_resolution
from middleware.notes import format_private_note, format_private_note_html, select_for_note
from middleware.preprocess import Normalizer
from settings import load_config, resolve_path


class BagOfWordsEmbedder:
    """Deterministic stand-in for the sentence-transformers model."""

    model_name = "test-bow"
    dim = 512

    def encode(self, texts):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in re.findall(r"[a-z']+", text.lower()):
                out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1
            norm = np.linalg.norm(out[i])
            if norm:
                out[i] /= norm
        return out


def closed(id, summary, resolution, **kw) -> Ticket:
    return Ticket(id=id, summary=summary, details=kw.pop("details", ""), resolution=resolution,
                  status="Closed", date_closed=kw.pop("date_closed", "2026-09-01T10:00:00"), **kw)


@pytest.fixture
def matcher(tmp_path):
    cfg = load_config()
    normalizer = Normalizer.from_file(resolve_path("synonyms.yaml"))
    embedder = BagOfWordsEmbedder()
    index = TicketIndex(tmp_path / "index.db", embedder, normalizer)
    index.upsert([
        closed(1, "CF-33 cant reach CAD", "Power-cycled the Cradlepoint modem, CAD reconnected.",
               client="Riverside Fire Dept", type="Standard Applications", subtype="CAD Applications"),
        closed(2, "tuffbook not connecting to dispatch", "Reapplied modem APN config, CAD back online.",
               client="Cedar County EMS"),
        closed(3, "toughbook wont connect to cad", "", client="Riverside Fire Dept"),
        closed(4, "toughbook not connecting to cad", "fixed", client="Riverside Fire Dept"),
        closed(5, "printer jammed", "Replaced fuser unit.", client="Riverside Fire Dept"),
    ])
    return Matcher(index, normalizer, embedder, cfg["matching"])


def test_finds_toughbook_cad_tickets_without_the_word_laptop(matcher):
    result = matcher.search(text="truck laptop wont connect to dispatch again", top_k=3)
    ids = [m.ticket.id for m in result.matches]
    assert set(ids[:2]) == {1, 2}
    assert result.concepts == ["cad", "toughbook"]


def test_empty_resolution_is_hidden_and_weak_one_ranked_lower(matcher):
    result = matcher.search(text="toughbook not connecting to cad", top_k=5)
    ids = [m.ticket.id for m in result.matches]
    assert 3 not in ids
    assert result.hidden_no_resolution == 1
    weak = next(m for m in result.matches if m.ticket.id == 4)
    assert weak.weak_resolution and weak.boosts["weak_resolution"] < 0
    # Ticket 4 has the most similar wording but the vague fix pushes it below a real one.
    assert ids.index(4) > ids.index(2)


def test_structured_boosts_apply_for_ticket_queries(matcher):
    query = Ticket(id=99, summary="cad not connecting on toughbook", client="Riverside Fire Dept",
                   type="Standard Applications", subtype="CAD Applications", status="New")
    result = matcher.search(query=query, top_k=5, now=datetime(2026, 9, 2))
    by_id = {m.ticket.id: m for m in result.matches}
    assert {"same_client", "same_type", "same_subtype", "shared_concepts", "recency"} <= set(by_id[1].boosts)
    assert "same_client" not in by_id[2].boosts


def test_feedback_adjusts_score_within_cap(matcher):
    def raw(result, tid):
        return next(m.raw_score for m in result.matches if m.ticket.id == tid)

    before = matcher.search(text="toughbook not connecting to cad", top_k=5)
    matcher.feedback_scores = lambda: {1: 5, 2: -1}
    after = matcher.search(text="toughbook not connecting to cad", top_k=5)
    assert raw(after, 1) - raw(before, 1) == pytest.approx(0.10)  # 5 votes * 0.03, capped at 0.10
    assert raw(after, 2) - raw(before, 2) == pytest.approx(-0.03)


def test_near_duplicates_do_not_tie_at_100_percent(matcher):
    result = matcher.search(text="toughbook not connecting to cad", top_k=5)
    assert result.matches[0].score == 1.0
    assert result.matches[0].raw_score > result.matches[1].raw_score


def test_excludes_the_query_ticket_itself(matcher):
    query = Ticket(id=1, summary="CF-33 cant reach CAD", status="Closed")
    ids = [m.ticket.id for m in matcher.search(query=query, top_k=5).matches]
    assert 1 not in ids


def test_note_skips_weak_resolutions(matcher):
    result = matcher.search(text="truck laptop wont connect to dispatch", top_k=5)
    assert 4 in [m.ticket.id for m in result.matches]
    to_post = select_for_note(result, top_k=3, min_score=0.3)
    assert to_post and 4 not in [m.ticket.id for m in to_post]

    note = format_private_note(to_post)
    assert note.startswith("🔎 Similar resolved tickets")
    assert "Fix: Power-cycled the Cradlepoint modem" in note
    assert "Fix: fixed" not in note
    assert note.rstrip().endswith("click Similar Tickets at the top of this ticket.")


def test_html_note_links_ticket_ids(matcher):
    result = matcher.search(text="truck laptop wont connect to dispatch", top_k=5)
    to_post = select_for_note(result, top_k=3, min_score=0.3)
    html = format_private_note_html(to_post, "https://halo.example/ticket?id={id}")
    for m in to_post:
        assert f'<a href="https://halo.example/ticket?id={m.ticket.id}">#{m.ticket.id}</a>' in html
    assert "<b>Fix:</b> Power-cycled the Cradlepoint modem" in html


def test_html_note_escapes_user_text(tmp_path):
    normalizer = Normalizer.from_file(resolve_path("synonyms.yaml"))
    embedder = BagOfWordsEmbedder()
    index = TicketIndex(tmp_path / "index.db", embedder, normalizer)
    index.upsert([closed(7, 'printer <script>alert("x")</script>', "Replaced the fuser & cleaned rollers.")])
    m = Matcher(index, normalizer, embedder, load_config()["matching"]).search(text="printer", top_k=1).matches
    html = format_private_note_html(m, "https://halo.example/ticket?id={id}")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "fuser &amp; cleaned" in html


def test_no_note_below_threshold(matcher):
    result = matcher.search(text="new hire needs a badge made", top_k=5)
    assert result.matches and not result.confident
    assert select_for_note(result, top_k=3, min_score=0.0) == []


@pytest.mark.parametrize("text,weak", [("", True), ("fixed", True), ("Done.", True),
                                       ("Replaced fuser unit; opened vendor ticket.", False)])
def test_weak_resolution(text, weak):
    assert is_weak_resolution(text, 20) is weak
