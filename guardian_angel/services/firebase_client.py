"""Firebase Admin initialization."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials

logger = logging.getLogger(__name__)


def get_firestore_client(
    project_id: str,
    *,
    service_account_path: str | None = None,
):
    """Return a Firestore client for ``project_id``.

    If ``service_account_path`` is set (or ``GOOGLE_APPLICATION_CREDENTIALS`` is in the
    environment), uses a **service account JSON file**. Otherwise uses Application Default
    Credentials (metadata server, gcloud, etc.).
    """

    from firebase_admin import firestore as fa_firestore

    path = service_account_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    path = path.strip() if isinstance(path, str) and path.strip() else None

    if not firebase_admin._apps:
        if path:
            resolved = Path(path).expanduser().resolve()
            if not resolved.is_file():
                raise FileNotFoundError(
                    f"GOOGLE_APPLICATION_CREDENTIALS file not found: {resolved}"
                )
            cred = credentials.Certificate(str(resolved))
            logger.info("Firebase Admin using service account file %s", resolved)
        else:
            cred = credentials.ApplicationDefault()
            logger.info("Firebase Admin using Application Default Credentials")

        firebase_admin.initialize_app(cred, {"projectId": project_id})
        logger.info("Firebase Admin initialized for project %s", project_id)

    return fa_firestore.client()
