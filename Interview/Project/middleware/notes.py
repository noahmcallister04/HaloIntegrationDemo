"""Formats the private note posted back to the Halo ticket.

Halo actions carry a plain-text ``note`` and an HTML ``note_html``; the agent UI shows the HTML,
which is where the ticket numbers become links to the past tickets.
"""
from __future__ import annotations

from html import escape

from middleware.matcher import Match, SearchResult

FOOTER = "More matches, details and 👍/👎 feedback: click Similar Tickets at the top of this ticket."


def select_for_note(result: SearchResult, top_k: int, min_score: float) -> list[Match]:
    """Matches worth posting: real fix notes, decent score, and only if the best clears the threshold.

    Weak resolutions ("fixed", "done") still show on the Similar Tickets page but add nothing to a note.
    """
    usable = [m for m in result.matches if not m.weak_resolution and m.score >= min_score]
    if not usable or usable[0].score < result.threshold:
        return []
    return usable[:top_k]


def _one_line(text: str | None, limit: int) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def format_private_note(matches: list[Match]) -> str:
    lines = ["🔎 Similar resolved tickets (auto-suggested)", ""]
    for m in matches:
        t = m.ticket
        where = " / ".join(p for p in (t.client, t.site) if p)
        lines.append(f'#{t.id} ({round(m.score * 100)}%) – {where} – "{_one_line(t.summary, 70)}"')
        lines.append(f"   Fix: {_one_line(t.resolution, 180)}")
    lines += ["", FOOTER]
    return "\n".join(lines)


def ticket_link(ticket_id: int, ticket_url: str) -> str:
    """ticket_url is a template like https://<tenant>/ticket?id={id}."""
    return ticket_url.format(id=ticket_id)


def format_private_note_html(matches: list[Match], ticket_url: str) -> str:
    items = []
    for m in matches:
        t = m.ticket
        where = " / ".join(p for p in (t.client, t.site) if p)
        href = escape(ticket_link(t.id, ticket_url), quote=True)
        items.append(
            f'<li><a href="{href}">#{t.id}</a> ({round(m.score * 100)}%) – {escape(where)} – '
            f"“{escape(_one_line(t.summary, 70))}”<br>"
            f"<b>Fix:</b> {escape(_one_line(t.resolution, 180))}</li>"
        )
    return (
        "<p><b>🔎 Similar resolved tickets</b> (auto-suggested)</p>"
        f"<ul>{''.join(items)}</ul>"
        f"<p>{escape(FOOTER)}</p>"
    )
