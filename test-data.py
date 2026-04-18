#!/usr/bin/env python3
"""Send the same mock victims as ``demo_data.demo_victims()`` via the ingestion API.

The main console uses :func:`guardian_angel.demo_data.demo_victims` when Firestore is
unavailable. Each victim row has its own ``geo`` and ``picture_ref``; the API stores
scene-level ``geo`` and ``picture`` on the transmission, so this script posts **one
transmission per victim** to preserve those fields (see ``firestore_store``).

Usage::

    uv run python test-data.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

# Allow ``python test-data.py`` without editable install
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = _ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _transmission_body(row: dict[str, str | None]) -> dict:
    """Build JSON body for POST /api/v1/transmissions from a demo_data row."""

    triage_entry: dict = {
        "id": row["id"],
        "color": row["color"],
        "description": row["description"],
        "boundingbox": {"width": 0, "height": 0, "x": 0, "y": 0},
    }
    body: dict = {
        "triage_system": "SALT",
        "picture": row.get("picture_ref") or "",
        "triage": [triage_entry],
    }
    geo = row.get("geo")
    if geo:
        body["geo"] = geo
    return body


def main() -> int:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="POST demo_data mock victims to Guardian Angel (one transmission each)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("GUARDIAN_ANGEL_BASE_URL", "http://127.0.0.1:8000"),
        help="API base URL (default: env GUARDIAN_ANGEL_BASE_URL or http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    secret = os.environ.get("GUARDIAN_ANGEL_API_SECRET") or os.environ.get(
        "GUARDIAN_ANGEL_SHARED_SECRET"
    )
    if not secret:
        print(
            "Missing GUARDIAN_ANGEL_API_SECRET (or GUARDIAN_ANGEL_SHARED_SECRET) in environment or .env",
            file=sys.stderr,
        )
        return 1

    try:
        import httpx
    except ImportError:
        print("Install httpx: uv sync", file=sys.stderr)
        return 1

    from guardian_angel.demo_data import demo_victims

    rows = demo_victims()
    base = args.base_url.rstrip("/")
    url = f"{base}/api/v1/transmissions"
    headers = {"Authorization": f"Bearer {secret}"}

    ok = 0
    for row in rows:
        payload = _transmission_body(row)
        r = httpx.post(url, json=payload, headers=headers, timeout=60.0)
        vid = row.get("id", "?")
        print(f"{r.status_code} victim {vid}", end=" ")
        try:
            print(r.json())
        except Exception:
            print(r.text)
        if r.is_error:
            return 1
        ok += 1

    print(f"Done: {ok} transmission(s) posted ({len(rows)} demo rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
