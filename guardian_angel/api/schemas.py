"""Response models for OpenAPI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from guardian_angel.triage import TRIAGE_COLOR_ORDER


class MetaResponse(BaseModel):
    service: str = "guardian-angel"
    version: str
    triage_system: str
    git_sha: str | None = None
    firestore: bool = Field(description="Whether Firestore is connected")


class VictimRow(BaseModel):
    id: str
    color: str
    description: str | None = None
    geo: str | None = None
    picture_ref: str | None = None
    last_transmission_id: str | None = None
    updated_at: datetime | None = None


class VictimsResponse(BaseModel):
    victims: list[VictimRow]
    total: int
    by_color: dict[str, int]


class TransmissionListItem(BaseModel):
    transmission_id: str
    received_at: datetime | None
    geo: str | None = None
    triage_system: str | None = None
    victim_count: int = 0
    payload: dict[str, Any]


class TransmissionListResponse(BaseModel):
    items: list[TransmissionListItem]
    next_cursor: str | None = None


class IngestResponse(BaseModel):
    transmission_id: str
    status: str = "created"


class MedicNoteItem(BaseModel):
    id: str
    notes: str
    created_at: datetime | None = None


class MedicNotesListResponse(BaseModel):
    items: list[MedicNoteItem]
    next_cursor: str | None = None


class MedicNoteCreatedResponse(BaseModel):
    note_id: str
    status: str = "created"


def empty_by_color() -> dict[str, int]:
    return {c: 0 for c in TRIAGE_COLOR_ORDER}
