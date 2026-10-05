# Project Context: Similar Resolved Tickets (HaloPSA Middleware)

## 1. Background

- **Company:** FeatherShark, a Managed Service Provider (MSP) that manages IT for **fire and EMS departments**.
- **Ticketing system:** **HaloPSA** ("Halo").
- **Me:** Noah, currently on the **service help desk**, applying to the **Applications team** (moving into a programming role).
- **Interview:** short **15-minute** interview on **Monday, October 5, 2026**. This project is a demo to show during it.
- **Build time:** about **1 day**. Basic infrastructure, **runs locally**.

### What the previous Applications developer built (avoid duplicating)
- **Invoice automation** in Halo: invoices from software licenses, IT services, new computers, etc. (including license reconciliation / billing audit).
- **Reports Dashboard:** service desk metrics such as tickets closed today, opened today, ticket kill rate, tickets older than X days.
- General theme: **middleware and automations** that improve productivity or surface insights.

This project should **complement** that work, not repeat it. His projects were mostly scheduled/batch (invoices, metrics). This one is **event-driven** (webhook in, action out) and helps technicians while they work.

---

## 2. Project Idea

### Name
**Similar Resolved Tickets** (working title)

### Problem
When technicians work a ticket, they often know "we've fixed this before" but have to scroll through old tickets or search Halo by hand. Searching is unreliable because **users write the tickets** and the summaries and descriptions are inconsistent: typos, vague wording ("it's broken again"), different names for the same device, forwarded email junk.

### Solution
Middleware that, when a ticket is created, finds the most similar **closed** tickets and posts them as a **private note on the ticket**, including **what fixed them**. Technicians see past fixes without leaving Halo.

There is also a small **lookup web page**: paste a ticket number or description and get the same results. Technicians can use it anytime, and it works well for the live demo.

### Example private note
```
🔎 Similar resolved tickets
#48213 (91%) – Station 4 – "Copier won't print from MDT"
   Fix: Cleared print spooler, reinstalled Ricoh PCL6 driver
#47790 (84%) – Station 4 – "printer jammed again??"
   Fix: Replaced fuser; vendor ticket opened with Ricoh
#45102 (78%) – Station 9 – "Can't print patient report"
   Fix: Default printer reset after Windows update
```

---

## 3. Architecture

```
New ticket in Halo (mock)
  → Webhook (ticket created) → Middleware (FastAPI)
  → Clean + normalize text
  → Similarity search over closed-ticket index
  → Rank (semantic score + structured boosts)
  → If top score ≥ threshold: POST private note back to ticket via Halo API

Ticket closed in Halo (mock)
  → Webhook (ticket closed) → embed ticket → add to index (stays current automatically)

Lookup page (browser)
  → enter ticket # or free text → same search → results with fixes + feedback buttons
```

### Components
| Component | Responsibility |
|---|---|
| `mock_halo/` | Fake Halo REST API (tickets, clients, assets, actions/notes) + webhook sender. Same shape as the real API so it can be swapped later |
| `halo_client.py` | Thin client for the Halo API (get ticket, list closed tickets, add private note). Base URL + OAuth2 client credentials from config. Stubbed for mock |
| `preprocess.py` | Text cleanup + synonym normalization |
| `indexer.py` | Builds/updates embeddings for closed tickets, stores in SQLite |
| `matcher.py` | Similarity search + ranking + threshold |
| `app.py` | FastAPI app: webhook endpoints, lookup page, feedback endpoint |
| `seed_data.py` | Generates realistic, deliberately messy fire/EMS tickets |

### Stack
- **Python 3.11+**
- **FastAPI + Uvicorn:** webhooks, mock API, lookup page
- **sentence-transformers** (`all-MiniLM-L6-v2`, ~90 MB, CPU, no API key): semantic embeddings
- **NumPy:** cosine similarity (fine at MSP scale, no vector DB)
- **rapidfuzz:** typo-tolerant matching against the synonym dictionary
- **SQLite:** tickets, embeddings, feedback
- **Plain HTML + minimal JS** for the lookup page
- Start everything with a single command (e.g. `python run.py`)

> Language is still open: if FeatherShark's Applications team mainly uses C# or PowerShell, consider matching it. Default is Python.

---

## 4. Matching Approach (handles inconsistent user-written tickets)

1. **Prefer technician-controlled fields.** Category/subcategory (often corrected at triage or close), client/site, linked asset, and **resolution notes** are more consistent than user descriptions.
2. **Text cleanup.** Strip email signatures, "Sent from my iPhone", greetings and reply chains. Lowercase, collapse whitespace.
3. **Fire/EMS synonym dictionary** (`synonyms.yaml`, editable):

   | Variants | Normalized |
   |---|---|
   | toughbook, cf-33, cf33, tuffbook, truck laptop, rugged laptop | `toughbook` |
   | mdt, mdc, mobile data terminal, truck computer | `mdt` |
   | printer, copier, mfp, priner, can't print | `printer` |
   | locked out, forgot password, can't log in, password reset | `account_access` |
   | epcr, patient report, charting software | `epcr` |
   | cad, dispatch, computer aided dispatch | `cad` |
   | station alerting, tones, alerting system | `station_alerting` |

4. **Semantic embeddings.** Embed `summary + description + resolution` for closed tickets. Embed `summary + description` for the incoming ticket. Cosine similarity.
5. **Structured boosts** (tunable weights in config):
   - same client/site: + boost
   - same category: + boost
   - same asset model: + boost
   - recency (more recent = slightly higher)
6. **Resolution quality filter.** Skip or rank lower any closed ticket with empty or very short resolution notes.
7. **Confidence threshold.** Only post a note if the top result is ≥ ~0.6, so technicians don't learn to ignore weak suggestions. Return the top 3.
8. **Feedback loop.** "Helpful / Not helpful" per suggestion, stored in SQLite and used to adjust ranking. Also gives a usefulness metric.

---

## 5. Data Model (SQLite)

```
tickets(
  id INTEGER PRIMARY KEY,
  client TEXT,          -- e.g. "Riverside Fire Dept"
  site TEXT,            -- e.g. "Station 4"
  category TEXT,
  subcategory TEXT,
  asset_model TEXT,     -- e.g. "Panasonic CF-33"
  summary TEXT,
  description TEXT,
  resolution TEXT,      -- null for open tickets
  status TEXT,          -- "open" | "closed"
  created_at TEXT,
  closed_at TEXT
)

embeddings(
  ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id),
  vector BLOB           -- float32 numpy array
)

notes(
  id INTEGER PRIMARY KEY,
  ticket_id INTEGER,
  body TEXT,
  is_private INTEGER,
  created_at TEXT
)

feedback(
  id INTEGER PRIMARY KEY,
  open_ticket_id INTEGER,
  suggested_ticket_id INTEGER,
  helpful INTEGER,      -- 1 / 0
  created_at TEXT
)
```

---

## 6. Endpoints

### Middleware
| Method | Path | Purpose |
|---|---|---|
| POST | `/webhooks/ticket-created` | Receive new ticket → search → post private note |
| POST | `/webhooks/ticket-closed` | Receive closed ticket → embed → add to index |
| GET | `/` | Lookup page |
| GET | `/api/similar?ticket_id=` or `?q=` | Search by ticket or free text, returns JSON |
| POST | `/api/feedback` | Record helpful / not helpful |

### Mock Halo (mimics real API shape)
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/token` | Fake OAuth2 client-credentials token |
| GET | `/api/Tickets` / `/api/Tickets/{id}` | List / get tickets |
| POST | `/api/Tickets` | Create ticket (fires `ticket-created` webhook) |
| POST | `/api/Tickets/{id}/close` | Close ticket with resolution (fires `ticket-closed` webhook) |
| POST | `/api/Actions` | Add note/action to a ticket (private flag) |

> Real Halo uses OAuth2 client credentials and REST resources like `/api/Tickets` and `/api/Actions`. **Verify exact endpoints and payloads against FeatherShark's Halo instance API docs** before going to production or quoting them in the interview.

---

## 7. Seed Data

- About **300 closed tickets** + a handful of open tickets for the demo.
- **Fictional** fire/EMS clients only (no real customer data), e.g. Riverside Fire Dept, Cedar County EMS, Lakeview Fire & Rescue, Pine Ridge Fire District.
- Sites: Station 1–12, Admin Office, Dispatch Center, Medic/Engine units.
- Common issue themes: Toughbook/MDT connectivity, CAD client errors, ePCR sync failures, printers/copiers, account lockouts/password resets, station alerting, VPN/cellular modems, Wi-Fi at stations, M365/Outlook, docking stations, monitor/peripheral issues.
- **Deliberately messy:** typos, vague summaries ("its broken again"), mixed device names, forwarded email junk, some wrong categories, some tickets with empty resolutions (to show the quality filter).
- Every theme has multiple realistic **resolutions** written in technician voice.

---

## 8. Demo Script (~4 minutes of the 15)

1. **Problem (30s):** "Technicians re-solve problems we've already fixed because searching old tickets is slow and user-written text is inconsistent."
2. **Live demo (2–3 min):**
   - Create a messy ticket: *"truck laptop wont connect to dispatch again"*.
   - A private note appears within seconds with 3 past Toughbook/CAD tickets and their fixes, **even though none contain the word "laptop."**
   - Use the lookup page to search a different issue live.
   - Close a new ticket, then show it appear in results right away.
3. **Architecture (1 min):** webhook → normalize → embed → rank → post note. Mock Halo can be swapped for real Halo.
4. **Path to production (30s):** real OAuth credentials, register webhooks in Halo, post notes via the actions API, run as a Windows service / container, backfill the index with historical closed tickets, track feedback to measure usefulness.

### Talking points
- Designed for messy data from the start (synonyms + semantic matching + technician fields).
- Event-driven middleware, a different pattern from the existing scheduled automations.
- Confidence threshold + feedback loop so technicians trust the output.
- Runs locally, no paid APIs, no customer data leaves the network.
- **Next steps:** auto-suggest category/priority, link to KB articles, flag recurring issues per site for account managers.

### Prep
- Record a 60-second backup video of the demo.
- Use only fictional data.

---

## 9. Build Plan (1 day)

| Time | Task |
|---|---|
| 1 hr | Project skeleton, SQLite schema, `seed_data.py` with messy fire/EMS tickets |
| 1.5 hr | Mock Halo API + `halo_client.py` + webhook firing |
| 2 hr | `preprocess.py` (cleanup + synonyms), `indexer.py`, `matcher.py` (embeddings + boosts + threshold) |
| 1.5 hr | Webhook endpoints that post private notes; ticket-closed indexing |
| 1.5 hr | Lookup page + feedback buttons |
| 30 min | README (setup, architecture diagram, path to production) + rehearse demo |

---

## 10. Out of Scope (for the demo)

- Real Halo credentials or production data
- Authentication on the lookup page
- LLM summarization (possible later add-on via a local model such as Ollama)
- Deployment / hosting