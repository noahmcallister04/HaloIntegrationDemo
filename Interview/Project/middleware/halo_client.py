"""Thin client for the Halo REST API using OAuth2 client credentials.

Talks to the mock by default. Pointing it at a real Halo instance means changing the
URLs/credentials in config.yaml and checking the field mapping in ``ticket_from_halo``.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Iterator

import httpx

log = logging.getLogger(__name__)


@dataclass
class Ticket:
    id: int
    summary: str
    details: str = ""
    client: str | None = None
    site: str | None = None
    type: str | None = None
    subtype: str | None = None
    asset_model: str | None = None
    status: str | None = None
    date_reported: str | None = None
    date_closed: str | None = None
    resolution: str | None = None

    @property
    def is_closed(self) -> bool:
        return (self.status or "").lower() in ("closed", "resolved")


def ticket_from_halo(data: dict) -> Ticket:
    # The one place Halo field names are mapped. Verify against the real instance's
    # API docs (Type/Subtype may surface as category fields, asset as a linked asset).
    return Ticket(
        id=int(data["id"]),
        summary=data.get("summary") or "",
        details=data.get("details") or "",
        client=data.get("client_name"),
        site=data.get("site_name"),
        type=data.get("type"),
        subtype=data.get("subtype"),
        asset_model=data.get("asset_model"),
        status=data.get("status"),
        date_reported=data.get("date_reported"),
        date_closed=data.get("date_closed"),
    )


class HaloClient:
    # Action outcomes that hold the fix when a ticket is closed.
    RESOLUTION_OUTCOMES = {"resolved", "closed", "resolution"}

    def __init__(
        self,
        base_url: str,
        auth_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "all",
        timeout: float = 10.0,
    ):
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._auth_url = auth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._token: str | None = None
        self._token_expiry = 0.0
        self._token_lock = threading.Lock()

    @classmethod
    def from_config(cls, cfg: dict) -> "HaloClient":
        h = cfg["halo"]
        return cls(h["base_url"], h["auth_url"], h["client_id"], h["client_secret"], h.get("scope", "all"))

    def close(self) -> None:
        self._http.close()

    def _get_token(self, force_refresh: bool = False) -> str:
        with self._token_lock:
            if not force_refresh and self._token and time.time() < self._token_expiry - 60:
                return self._token
            resp = self._http.post(
                self._auth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": self._scope,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            self._token = body["access_token"]
            self._token_expiry = time.time() + float(body.get("expires_in", 3600))
            return self._token

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        # Retry once with a fresh token on 401 (expired token, or Halo restarted).
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {self._get_token(force_refresh=attempt > 0)}"}
            resp = self._http.request(method, path, headers=headers, **kwargs)
            if resp.status_code == 401 and attempt == 0:
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("unreachable")

    def get_ticket(self, ticket_id: int) -> Ticket:
        return ticket_from_halo(self._request("GET", f"/api/Tickets/{ticket_id}").json())

    def iter_closed_tickets(self, page_size: int = 100) -> Iterator[Ticket]:
        page = 1
        while True:
            body = self._request(
                "GET", "/api/Tickets",
                params={"closed_only": "true", "page_size": page_size, "page_no": page},
            ).json()
            tickets = body.get("tickets", [])
            for t in tickets:
                yield ticket_from_halo(t)
            if len(tickets) < page_size:
                return
            page += 1

    def get_actions(self, ticket_id: int) -> list[dict]:
        return self._request("GET", "/api/Actions", params={"ticket_id": ticket_id}).json().get("actions", [])

    def get_resolution(self, ticket_id: int) -> str | None:
        """Returns the note on the most recent closing action, if any."""
        actions = sorted(self.get_actions(ticket_id), key=lambda a: (a.get("datetime") or "", a.get("id") or 0))
        for action in reversed(actions):
            if (action.get("outcome") or "").lower() in self.RESOLUTION_OUTCOMES:
                return action.get("note") or ""
        return None

    def get_closed_ticket(self, ticket_id: int) -> Ticket:
        ticket = self.get_ticket(ticket_id)
        ticket.resolution = self.get_resolution(ticket_id)
        return ticket

    def add_private_note(
        self, ticket_id: int, note: str, note_html: str | None = None, who: str | None = None
    ) -> int | None:
        resp = self._request(
            "POST", "/api/Actions",
            json=[{
                "ticket_id": ticket_id,
                "note": note,
                "note_html": note_html,
                "outcome": "Private Note",
                "hiddenfromuser": True,
                "who": who,
            }],
        )
        data = resp.json()
        first = data[0] if isinstance(data, list) and data else data
        return first.get("id") if isinstance(first, dict) else None
