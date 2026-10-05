# Similar Resolved Tickets

Event-driven middleware for HaloPSA. When a ticket is created, it finds the most similar
**closed** tickets and posts them, with **what fixed them**, as a private note on the new
ticket. Technicians see past fixes without leaving Halo.

It is built for messy, user-written tickets: typos, vague summaries, forwarded-email junk,
and five names for the same device.

```
New ticket in Halo ──webhook──▶ Middleware ──▶ clean + normalize text ──▶ embed
                                     │                                     │
                                     ◀── rank: semantic + structured boosts ◀┘
                                     │
                                     └──▶ score ≥ threshold? ──▶ POST private note (Halo Actions API)

Ticket closed ──webhook──▶ fetch fix from closing action ──▶ embed ──▶ added to index immediately

Ticket in Halo ──"Similar Tickets" Custom Button──▶ new window: /similar?ticket_id=$FAULTID
                                                  ──▶ same search ──▶ results + 👍/👎 feedback
```

Technicians get the results in two places:

- **The private note.** It lands on the new ticket within seconds, listing the top matches and
  their fixes. Each past ticket number links to that ticket.
- **The Similar Tickets window.** The **Similar Tickets** button at the top of the ticket opens a
  separate window with more matches, a score breakdown and 👍/👎 feedback. Clicking
  a past ticket opens it in that window, and Back (the ticket's ← arrow or the browser's)
  returns to the list of similar tickets. The ticket you're working on stays open in the main
  window.

Everything runs locally with fictional data. There are no paid APIs and no customer data.

## Run it

Requires Python 3.11+ (tested on 3.12, Windows).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

`run.py` starts two services:

| Service | URL | What it is |
|---|---|---|
| Mock Halo | http://127.0.0.1:8001/ | Stand-in for HaloPSA: the ticket UI and a Halo-style REST API |
| Middleware | http://127.0.0.1:8000/ | Webhooks, matching, the bot note, and the Similar Tickets page |

On the first run the mock Halo is seeded with ~300 closed tickets and 5 open ones. The embedding
model (`all-MiniLM-L6-v2`, ~90 MB) is downloaded once and then cached, so later runs work
offline. `run.py --reseed` regenerates the demo data and rebuilds the index.

```powershell
.\.venv\Scripts\python.exe -m pytest                    # unit tests (fake embedder, fast)
.\.venv\Scripts\python.exe evaluate.py --summary-only   # match quality on held-out tickets
```

## Demo walkthrough

1. Open Mock Halo, click **+ New**, choose the **Truck laptop won't connect to dispatch** preset,
   and click **Log ticket**.
2. The ticket opens. Within a couple of seconds the **Similar Tickets Bot** private note appears
   with three past Toughbook/CAD fixes, even though none of them say "laptop". Click a ticket
   number in the note to open that past ticket.
3. Click **Similar Tickets ↗** at the top of the ticket. A window opens showing what the ticket
   was "understood as" (`toughbook won't connect to cad again`), the matches with their fixes,
   and **Why this match?** for each one. Click 👍 or 👎 on a match.
4. Click a past ticket number in that window, then ← to come back to the similar tickets.
5. In the main window, click **Close Ticket** on any open ticket and enter a fix. It's indexed
   immediately and shows up in later searches.

Deep links work too, e.g. http://127.0.0.1:8001/#ticket=45306.

## The mock Halo

The mock follows the layout of the Halo agent UI so the integration can be shown in context. It
uses a generic "M" mark and is labeled as a local demo, not HaloPSA.

- **Ticket list:** ID, Client, Contact, Summary, SLA Time Left, Priority, Status, Channel and
  Ticket Age. SLA bars go green → yellow → orange as time runs down and turn red with a negative
  time once breached. Every column sorts, the view switches between Open, Closed and All, and
  the list refreshes every few seconds.
- **Ticket view:** a details panel (client, site, contact, channel, type, priority, SLA, agent,
  asset, dates, time taken) and the action thread, newest first. Private notes are yellow,
  emails to the user are blue, customer replies are gray, and the closing note is green. The
  original request shows at the bottom as "Logged via Email/Phone/Portal". **Add Note**,
  **Email User** and **Close Ticket** work, and the thread refreshes every 2 seconds so the
  bot's note appears without reloading.
- **Custom Button:** the **Similar Tickets ↗** button comes from `mock_halo.custom_buttons` in
  [config.yaml](config.yaml), the same URL-with-`$FAULTID` setup as a real Halo Custom Button.
- **Notes with HTML:** actions can carry a plain `note` and an HTML `note_html`, as in Halo. The
  UI renders the HTML through an allowlist sanitizer: basic formatting, and links only to
  `http(s)` or `#`.

### Seed data

[seed_data.py](seed_data.py) generates fictional fire/EMS clients (Riverside Fire Dept, Cedar
County EMS, Lakeview Fire & Rescue, Pine Ridge Fire District) across 27 problem types: CAD and
Toughbook connectivity, vehicle modems, ePCR sync, printers, station alerting, Wi-Fi, accounts,
phishing and more.

- **Deliberately messy:** typos, vague summaries ("help!!"), mixed device names, forwarded-email
  junk, some wrong categories, and some tickets closed with no or useless notes ("fixed"), so
  the quality filter has something to filter.
- **Realistic threads:** every closed ticket has a back-and-forth (about 1,300 actions in all):
  - phone-call and triage notes ("NetCloud shows the Medic 6 modem offline…")
  - questions emailed to the user ("What color are the lights on the Cradlepoint?")
  - the user's replies, typos and "Sent from my iPhone" included
  - follow-ups when the user goes quiet, and their "sorry, was on shift" reply
  - "can you confirm it's working?" before the closing note with the fix
- **Open tickets:** five open tickets in different SLA states, each with a thread in progress.

Threads use their own random seed, so ticket text and fixes stay the same if the thread
templates change. Matching uses each ticket's summary, details and fix, not the thread.

## How matching handles messy tickets

1. **Cleanup** ([middleware/preprocess.py](middleware/preprocess.py)) strips greetings,
   signatures, "Sent from my iPhone", external-sender banners and forwarded headers. It keeps
   the forwarded body.
2. **Synonyms** ([synonyms.yaml](synonyms.yaml), editable) map variants to one term:
   `truck laptop`, `CF-33`, `tuffbook` → `toughbook`; `dispatch` → `cad`. Single words are
   matched typo-tolerantly with rapidfuzz (`toughbok`, `priner`).
3. **Semantic similarity** uses sentence-transformers on CPU with cosine similarity in NumPy.
   Each closed ticket has two vectors, the problem alone and the problem + fix, and the better
   match counts.
4. **Structured boosts** ([config.yaml](config.yaml) → `matching.weights`) are added for the
   same client/site, Type/Subtype or asset model, shared concepts, recency, and technician
   feedback.
5. **Resolution quality:** tickets closed with no notes are hidden. Generic notes ("fixed",
   "done") are ranked lower and never posted.
6. **Confidence threshold:** a note is posted only when the best match scores ≥ 0.60, so
   technicians don't learn to ignore it.

The Similar Tickets window shows what the ticket was "understood as" and a per-result
**Why this match?** score breakdown.

### Measured on the seed data (`evaluate.py`, leave-one-out)

| Query uses | Top-1 same problem | Top-1 precision when a note is posted |
|---|---|---|
| Summary only (harder, often vague) | 88% | 94% |
| Summary + details | 100% | 100% |

The seed tickets come from shared templates, so these numbers are optimistic. The real test is
backfilling FeatherShark's history and tracking the 👍/👎 helpful rate (shown at the bottom of
the Similar Tickets window).

## Project layout

| Path | Responsibility |
|---|---|
| [run.py](run.py) | Starts both services with one command; seeds on first run |
| [config.yaml](config.yaml) | URLs, credentials, thresholds, boost weights, the mock's Custom Button |
| [settings.py](settings.py) | Loads config, with environment-variable overrides for secrets |
| [synonyms.yaml](synonyms.yaml) | Editable fire/EMS synonym dictionary |
| [seed_data.py](seed_data.py) | Generates the messy fictional tickets and their threads |
| [mock_halo/app.py](mock_halo/app.py) | Fake Halo API: OAuth2 token, `/api/Tickets`, `/api/Actions`, webhooks, UI endpoints |
| [mock_halo/db.py](mock_halo/db.py) | Mock Halo storage (SQLite), priority matrix, SLA dates |
| [mock_halo/reference.py](mock_halo/reference.py) | Types/subtypes from the Halo field list, fictional clients and sites |
| [mock_halo/static/index.html](mock_halo/static/index.html) | The mock Halo ticket list and ticket view |
| [middleware/halo_client.py](middleware/halo_client.py) | Halo API client (client credentials, token refresh, field mapping) |
| [middleware/preprocess.py](middleware/preprocess.py) | Text cleanup and synonym normalization |
| [middleware/indexer.py](middleware/indexer.py) | Embeddings, SQLite persistence, in-memory index, backfill sync |
| [middleware/matcher.py](middleware/matcher.py) | Similarity search, boosts, quality filter |
| [middleware/notes.py](middleware/notes.py) | Picks what goes in the note; formats it as text and linked HTML |
| [middleware/service.py](middleware/service.py) | Webhook handling, note posting, feedback, stats |
| [middleware/app.py](middleware/app.py) | FastAPI endpoints and the Similar Tickets page |
| [middleware/static/similar.html](middleware/static/similar.html) | The Similar Tickets window opened from a ticket |
| [evaluate.py](evaluate.py) | Leave-one-out match quality report |
| [tests/](tests/) | Unit tests for cleanup, synonyms, ranking, note selection and HTML escaping |

### Middleware endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/webhooks/ticket-created` | Search, then post a private note (requires `X-Webhook-Secret`) |
| POST | `/webhooks/ticket-closed` | Fetch resolution, then add to the index |
| GET | `/similar?ticket_id=` | Similar Tickets page for the Halo Custom Button (not framable: CSP `frame-ancestors 'none'`) |
| GET | `/api/similar?ticket_id=` or `?q=` | Search; returns JSON with the score breakdown and ticket links |
| POST | `/api/feedback` | Helpful / not helpful on a suggestion |
| GET | `/api/stats` | Indexed count, notes posted, helpful rate |

Webhooks only trust the ticket id; the ticket is re-fetched from the Halo API. Duplicate
webhooks for the same ticket are ignored.

### Mock Halo API

Shaped like Halo's REST API so the middleware's client can be pointed at a real instance.

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/token` | OAuth2 client-credentials token |
| GET | `/api/Tickets`, `/api/Tickets/{id}` | List (paged, `closed_only` / `open_only`) / get tickets |
| POST | `/api/Tickets` | Create ticket(s); fires the ticket-created webhook |
| POST | `/api/Tickets/{id}/close` | Close with a resolution; fires the ticket-closed webhook |
| GET / POST | `/api/Actions` | List a ticket's actions / add notes (`note`, `note_html`, `hiddenfromuser`) |

The `/ui/...` endpoints serve the mock's own web UI and aren't part of the Halo-style API.

## Path to production

- **Credentials:** create a Halo API application (client credentials) and set `HALO_BASE_URL`,
  `HALO_AUTH_URL`, `HALO_CLIENT_ID`, `HALO_CLIENT_SECRET` and `WEBHOOK_SECRET` as environment
  variables. Then run `python run.py --no-mock`.
- **Webhooks:** register ticket-created and ticket-closed webhooks in Halo pointing at
  `/webhooks/...`, sending the `X-Webhook-Secret` header.
- **Custom Button:** in Halo, add a ticket Custom Button named "Similar Tickets" with the URL
  `https://<middleware-host>/similar?ticket_id=$FAULTID` and "Open in New Tab" enabled. Halo
  replaces `$FAULTID` with the ticket number. Real Halo opens it in a new browser tab; the mock
  opens a sized popup window. Add `&theme=light` or `&theme=dark` to match the agents' Halo
  theme; without it the page follows the OS setting.
- **Ticket links:** set `halo.ticket_url` (or `HALO_TICKET_URL`) to the instance's ticket link
  format so ticket numbers in the note and the Similar Tickets window open the right ticket.
- **Backfill:** on startup the middleware indexes every closed ticket it hasn't seen. The same
  sync catches up on anything missed while it was down.
- **Hosting:** run as a Windows service (e.g. NSSM) or a container on an internal host. No
  ticket data leaves the network, and there are no paid APIs.

### To verify against FeatherShark's Halo instance

These assumptions are isolated in one place each so they're quick to change:

- **Field names** (`type`/`subtype`, `client_name`, `site_name`, asset): `ticket_from_halo()` in
  [halo_client.py](middleware/halo_client.py).
- **Where the fix lives:** currently the most recent action with outcome "Resolved"
  (`HaloClient.get_resolution`). It may be a closure-note field or a different outcome name.
- **Note format and links:** notes are posted with a plain `note` and an HTML `note_html`.
  Confirm the API accepts `note_html`, and confirm the ticket link format, likely
  `https://<tenant>.halopsa.com/ticket?id={id}`.
- **Closing a ticket:** the mock uses `POST /api/Tickets/{id}/close` for convenience. Real Halo
  closes tickets via an action with a status change. The middleware never closes tickets, so
  this only affects the mock.
- **Priority:** the mock derives priority from a standard Impact × Urgency matrix
  ([mock_halo/db.py](mock_halo/db.py)). Confirm the real matrix.
- **Back navigation:** the mock's ← arrow returns to the Similar Tickets window. Real Halo's own
  back arrow is outside our control, so there the browser's Back button does it.

## Next steps

- Include technicians' private notes in matching; they often hold the real diagnosis
  ("Intune shows the device certificate expired")
- Auto-suggest Type/Subtype and priority on new tickets from the same matches
- Link matching KB articles alongside past tickets
- Flag recurring issues per site (e.g. the same modem failing monthly) for account managers
