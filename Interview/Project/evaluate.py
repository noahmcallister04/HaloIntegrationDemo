"""Measures match quality on the seeded data (leave-one-out).

Each sampled closed ticket is treated as if it had just been opened: we search for it with
itself excluded and check whether the suggestions are the same kind of problem (scenario
labels written by seed_data.py). Reads the index directly, so the services needn't be running,
but the index must have been built once (python run.py).

    python evaluate.py [--sample 100] [--summary-only]

The seed data is generated from shared templates, so full-text leave-one-out is optimistic.
--summary-only is the harder case: just the (often vague, typo'd) user-written title.
"""
from __future__ import annotations

import argparse
import json
import random

from middleware import db
from middleware.halo_client import Ticket
from middleware.service import SimilarTicketsService
from seed_data import LABELS_PATH
from settings import load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--summary-only", action="store_true", help="query with the summary alone")
    args = parser.parse_args()

    cfg = load_config()
    service = SimilarTicketsService(cfg)
    service.index.load()
    if not len(service.index):
        raise SystemExit("Index is empty - run `python run.py` once first.")
    labels = {int(k): v for k, v in json.loads(LABELS_PATH.read_text(encoding="utf-8")).items()}

    with db.connect(service.db_path) as conn:
        rows = conn.execute("SELECT * FROM indexed_tickets").fetchall()
    rows = [r for r in rows if r["id"] in labels]
    random.Random(7).shuffle(rows)
    rows = rows[: args.sample]

    threshold = float(cfg["matching"]["post_threshold"])
    top1 = top3 = posted = posted_correct = 0
    for r in rows:
        query = Ticket(
            id=r["id"], summary=r["summary"], details="" if args.summary_only else r["details"],
            client=r["client"], site=r["site"],
            type=r["type"], subtype=r["subtype"], asset_model=r["asset_model"], status="New",
        )
        result = service.matcher.search(query=query, top_k=3)
        if not result.matches:
            continue
        want = labels[r["id"]]
        got = [labels.get(m.ticket.id) for m in result.matches]
        top1 += got[0] == want
        top3 += want in got
        if result.confident:
            posted += 1
            posted_correct += got[0] == want

    n = len(rows)
    print(f"Evaluated {n} held-out tickets ({'summary only' if args.summary_only else 'summary + details'})")
    print(f"  Top-1 same problem:        {top1 / n:.0%}")
    print(f"  Same problem in top 3:     {top3 / n:.0%}")
    print(f"  Would post a note (>= {threshold:.2f}): {posted / n:.0%}")
    if posted:
        print(f"  Top-1 precision when posted: {posted_correct / posted:.0%}")


if __name__ == "__main__":
    main()
