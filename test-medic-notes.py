#!/usr/bin/env python3
"""Smoke-test ``POST /api/v1/medicnotes`` against a Guardian Angel server.

Share this file with a colleague. They need:

- **Python 3.10+**
- Packages: ``httpx``, ``python-dotenv`` (or run from the repo with ``uv sync``)
- A **``.env``** next to this script (or in the current directory) containing::

    GUARDIAN_ANGEL_API_SECRET=<same shared secret as the server>
    # Optional — defaults to local dev:
    # GUARDIAN_ANGEL_BASE_URL=http://127.0.0.1:8000

Or export those variables in the shell instead of using a file.

Usage::

    uv run python test-medic-notes.py
    python test-medic-notes.py --notes "Custom note text"
    python test-medic-notes.py --base-url https://your-deployment.example.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (_ROOT / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return


DEFAULT_NOTES = (
    "This is an example note from a person transcribed by AI. "
    "(Sent by test-medic-notes.py — safe to delete in Firestore.)"
)


def main() -> int:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="POST a medic note to Guardian Angel (POST /api/v1/medicnotes)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("GUARDIAN_ANGEL_BASE_URL", "http://127.0.0.1:8000"),
        help="API base URL (default: env GUARDIAN_ANGEL_BASE_URL or http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--notes",
        default=os.environ.get("GUARDIAN_ANGEL_TEST_MEDIC_NOTE", DEFAULT_NOTES),
        help="String body field 'notes' (default: built-in sample text)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON payload and URL only; do not POST",
    )
    args = parser.parse_args()

    secret = os.environ.get("GUARDIAN_ANGEL_API_SECRET") or os.environ.get(
        "GUARDIAN_ANGEL_SHARED_SECRET"
    )
    if not secret and not args.dry_run:
        print(
            "Missing GUARDIAN_ANGEL_API_SECRET (or GUARDIAN_ANGEL_SHARED_SECRET). "
            "Add it to .env or your environment.",
            file=sys.stderr,
        )
        return 1

    payload = {"notes": args.notes}
    base = args.base_url.rstrip("/")
    url = f"{base}/api/v1/medicnotes"

    if args.dry_run:
        print("DRY RUN — would POST to:", url)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    try:
        import httpx
    except ImportError:
        print("Install httpx:  pip install httpx   or   uv sync", file=sys.stderr)
        return 1

    r = httpx.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {secret}"},
        timeout=60.0,
    )
    print(f"{r.status_code}  POST {url}")
    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)
    return 0 if r.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
