"""Medic notes ingestion payload."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MedicNotesPayload(BaseModel):
    """POST /api/v1/medicnotes body."""

    notes: str = Field(..., min_length=1, description="Free-text note from transcription or operator")
