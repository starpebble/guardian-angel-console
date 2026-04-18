"""SALT triage color vocabulary (see GUARDIAN_ANGEL_SPEC.md §6.2)."""

from __future__ import annotations

from typing import Literal

TriageColor = Literal["red", "yellow", "green", "gray", "black"]

TRIAGE_COLOR_ORDER: tuple[TriageColor, ...] = (
    "red",
    "yellow",
    "green",
    "gray",
    "black",
)

# Human-readable labels; shown next to color swatches (not color-only).
TRIAGE_LABELS: dict[TriageColor, str] = {
    "red": "Immediate",
    "yellow": "Delayed",
    "green": "Minimal",
    "gray": "Ambiguous",
    "black": "Expectant",
}
