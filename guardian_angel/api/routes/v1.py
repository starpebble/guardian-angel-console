"""`/api/v1/*` routes."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from guardian_angel import __version__
from guardian_angel.api.deps import require_ingestion_secret
from guardian_angel.api.schemas import (
    IngestResponse,
    MedicNoteCreatedResponse,
    MedicNoteItem,
    MedicNotesListResponse,
    MetaResponse,
    TransmissionListItem,
    TransmissionListResponse,
    VictimRow,
    VictimsResponse,
    empty_by_color,
)
from guardian_angel.models.medic_notes import MedicNotesPayload
from guardian_angel.models.transmission import TransmissionPayload
from guardian_angel.services.firestore_store import FirestoreStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


def _get_store(request: Request) -> FirestoreStore | None:
    return getattr(request.app.state, "store", None)


@router.get("/meta", response_model=MetaResponse)
async def api_meta(request: Request) -> MetaResponse:
    settings = request.app.state.settings
    return MetaResponse(
        version=__version__,
        triage_system=settings.triage_system_label,
        git_sha=settings.git_sha,
        firestore=_get_store(request) is not None,
    )


@router.post(
    "/transmissions",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_ingestion_secret)],
)
async def post_transmissions(
    request: Request,
    payload: TransmissionPayload,
) -> IngestResponse:
    store = _get_store(request)
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore is not configured; cannot persist transmissions.",
        )

    def _ingest() -> str:
        return store.ingest_transmission(payload)

    try:
        tid = await run_in_threadpool(_ingest)
    except Exception:
        logger.exception("Failed to persist transmission")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist transmission.",
        ) from None

    return IngestResponse(transmission_id=tid)


@router.get("/victims", response_model=VictimsResponse)
async def get_victims(request: Request) -> VictimsResponse:
    store = _get_store(request)
    if store is None:
        return VictimsResponse(victims=[], total=0, by_color=empty_by_color())

    def _read() -> tuple[list[dict], dict]:
        stats = store.get_stats()
        rows = store.list_victims()
        return rows, stats

    try:
        rows, stats = await run_in_threadpool(_read)
    except Exception:
        logger.exception("Failed to read victims")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read victims.",
        ) from None

    victims = [
        VictimRow(
            id=str(r.get("victim_id") or r.get("id")),
            color=str(r.get("color", "")),
            description=r.get("description"),
            geo=r.get("geo"),
            picture_ref=r.get("picture_ref"),
            last_transmission_id=r.get("last_transmission_id"),
            updated_at=r.get("_updated_at"),
        )
        for r in rows
    ]
    return VictimsResponse(
        victims=victims,
        total=stats["total"],
        by_color=stats["by_color"],
    )


@router.get("/transmissions", response_model=TransmissionListResponse)
async def get_transmissions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(description="Document id of last item from previous page")] = None,
) -> TransmissionListResponse:
    store = _get_store(request)
    if store is None:
        return TransmissionListResponse(items=[], next_cursor=None)

    def _read() -> tuple[list[dict], str | None]:
        return store.list_transmissions(limit=limit, cursor=cursor)

    try:
        raw_items, next_c = await run_in_threadpool(_read)
    except Exception:
        logger.exception("Failed to list transmissions")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list transmissions.",
        ) from None

    items = [
        TransmissionListItem(
            transmission_id=r["transmission_id"],
            received_at=r["received_at"],
            geo=r.get("geo"),
            triage_system=r.get("triage_system"),
            victim_count=int(r.get("victim_count", 0)),
            payload=r.get("payload") or {},
        )
        for r in raw_items
    ]
    return TransmissionListResponse(items=items, next_cursor=next_c)


@router.post(
    "/medicnotes",
    response_model=MedicNoteCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_ingestion_secret)],
    tags=["medicnotes"],
)
async def post_medicnotes(
    request: Request,
    payload: MedicNotesPayload,
) -> MedicNoteCreatedResponse:
    """Append one document to the medic notes Firestore collection (same auth as transmissions)."""

    store = _get_store(request)
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore is not configured; cannot persist medic notes.",
        )

    def _write() -> str:
        return store.add_medic_note(payload.notes)

    try:
        note_id = await run_in_threadpool(_write)
    except Exception:
        logger.exception("Failed to persist medic note")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist medic note.",
        ) from None

    return MedicNoteCreatedResponse(note_id=note_id)


@router.get("/medicnotes", response_model=MedicNotesListResponse, tags=["medicnotes"])
async def get_medicnotes(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(description="Document id of last item from previous page")] = None,
) -> MedicNotesListResponse:
    store = _get_store(request)
    if store is None:
        return MedicNotesListResponse(items=[], next_cursor=None)

    def _read() -> tuple[list[dict], str | None]:
        return store.list_medic_notes(limit=limit, cursor=cursor)

    try:
        raw, next_c = await run_in_threadpool(_read)
    except Exception:
        logger.exception("Failed to list medic notes")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list medic notes.",
        ) from None

    items = [
        MedicNoteItem(
            id=r["id"],
            notes=r["notes"],
            created_at=r.get("created_at"),
        )
        for r in raw
    ]
    return MedicNotesListResponse(items=items, next_cursor=next_c)
