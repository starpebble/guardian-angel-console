"""FastAPI dependencies (auth, app state)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger(__name__)


def _hash_digest(s: str) -> bytes:
    return hashlib.sha256(s.encode("utf-8")).digest()


def _constant_time_api_key_match(provided: str, expected: str) -> bool:
    """Compare API keys without requiring equal length (SHA-256 then hmac.compare_digest)."""

    return hmac.compare_digest(_hash_digest(provided), _hash_digest(expected))


def parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def require_ingestion_secret(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_guardian_angel_token: Annotated[str | None, Header(alias="X-Guardian-Angel-Token")] = None,
) -> None:
    settings = request.app.state.settings
    expected = settings.effective_api_secret()
    if not expected:
        logger.error("API rejected: GUARDIAN_ANGEL_API_SECRET not configured")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion API is not configured (missing API secret).",
        )
    provided = parse_bearer(authorization) or (x_guardian_angel_token or "").strip() or None
    if not provided or not _constant_time_api_key_match(provided, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing credentials.",
        )
