"""Starts the mock Halo instance and the middleware with one command.

    python run.py            # seed on first run, then start both services
    python run.py --reseed   # regenerate demo data and rebuild the index
    python run.py --no-mock  # middleware only (e.g. pointed at a real Halo via config/env)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import httpx

from settings import PROJECT_ROOT, load_config, resolve_path


def start(target: str, host: str, port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", target, "--host", host, "--port", str(port), "--log-level", "info"],
        cwd=PROJECT_ROOT,
        # Windows without Developer Mode can't symlink the model cache; harmless, so don't warn.
        env=os.environ | {"HF_HUB_DISABLE_SYMLINKS_WARNING": "1"},
    )


def wait_for(url: str, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"Process for {url} exited with code {proc.returncode}")
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit(f"Timed out waiting for {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reseed", action="store_true", help="regenerate demo data and rebuild the index")
    parser.add_argument("--no-mock", action="store_true", help="run only the middleware")
    args = parser.parse_args()

    cfg = load_config()
    mw, mock = cfg["middleware"], cfg["mock_halo"]
    halo_db, index_db = resolve_path(mock["db_path"]), resolve_path(mw["db_path"])

    if not args.no_mock and (args.reseed or not halo_db.exists()):
        import seed_data

        counts = seed_data.seed()
        print(f"Seeded mock Halo with {counts['closed']} closed + {counts['open']} open tickets")
        # Ticket ids are reused by a reseed, so the old index no longer lines up.
        index_db.unlink(missing_ok=True)

    procs: list[subprocess.Popen] = []
    try:
        if not args.no_mock:
            procs.append(start("mock_halo.app:app", mock["host"], mock["port"]))
            wait_for(f"http://{mock['host']}:{mock['port']}/health", procs[-1], timeout=30)
        procs.append(start("middleware.app:app", mw["host"], mw["port"]))
        print("Starting middleware (first run downloads the embedding model, ~90 MB)...")
        wait_for(f"http://{mw['host']}:{mw['port']}/health", procs[-1], timeout=600)

        print("\n" + "=" * 60)
        if not args.no_mock:
            print(f"  Mock Halo:  http://{mock['host']}:{mock['port']}/")
            print("              open a ticket -> 'Similar Tickets' button")
        print(f"  Halo Custom Button URL:  {mw['public_url'].rstrip('/')}/similar?ticket_id=$FAULTID")
        print("  Ctrl+C to stop")
        print("=" * 60 + "\n", flush=True)
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
