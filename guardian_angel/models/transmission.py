"""Transmission ingestion models (GUARDIAN_ANGEL_SPEC.md §6)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TriageColor(StrEnum):
    red = "red"
    yellow = "yellow"
    green = "green"
    gray = "gray"
    black = "black"


class BoundingBox(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    width: float | int
    height: float | int
    x: float | int
    y: float | int


class VictimTriageEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    color: TriageColor
    bounding_box: BoundingBox | None = Field(default=None, alias="boundingbox")
    description: str | None = None


class TransmissionPayload(BaseModel):
    """Top-level POST body; unknown fields are kept for Firestore storage."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )

    schema_version: str | int | None = None
    picture: str | None = None
    geo: str | None = None
    triage_system: str | None = Field(default=None, alias="triage-system")
    triage: list[VictimTriageEntry] = Field(default_factory=list)

    def to_stored_dict(self) -> dict[str, Any]:
        """JSON/Firestore-safe dict including extra keys and nested data."""

        base = self.model_dump(mode="json", exclude_none=False)
        extras = getattr(self, "__pydantic_extra__", None) or {}
        out = {**base, **extras}
        return out
