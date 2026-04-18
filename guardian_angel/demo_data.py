"""Placeholder victim rows for the main console until Firebase/API wiring exists."""

from __future__ import annotations

from guardian_angel.triage import TRIAGE_COLOR_ORDER, TriageColor


def demo_victims() -> list[dict[str, str | None]]:
    """Representative rows for UI testing; replace with Firestore reads later."""
    rows: list[dict[str, str | None]] = [
        {
            "id": "T1V1",
            "color": "red",
            "description": "Bleeding, impaled object in leg; responsive.",
            "geo": "37.7749 -122.4194",
            "picture_ref": "hex:…a1f2",
        },
        {
            "id": "T1V2",
            "color": "green",
            "description": "Awake, breathing, ambulatory; no visible hemorrhage.",
            "geo": "37.7751 -122.4190",
            "picture_ref": "hex:…b3c4",
        },
        {
            "id": "T1V3",
            "color": "yellow",
            "description": "Altered mental status; possible head injury.",
            "geo": "37.7746 -122.4198",
            "picture_ref": "hex:…d5e6",
        },
        {
            "id": "T1V4",
            "color": "gray",
            "description": "Unable to assess — obscured by debris.",
            "geo": None,
            "picture_ref": "hex:…f708",
        },
        {
            "id": "T1V5",
            "color": "black",
            "description": "No spontaneous respirations after airway opening.",
            "geo": "37.7750 -122.4192",
            "picture_ref": "hex:…9012",
        },
    ]
    return rows


def aggregate_counts(victims: list[dict[str, str | None]]) -> dict[TriageColor, int]:
    counts: dict[TriageColor, int] = {c: 0 for c in TRIAGE_COLOR_ORDER}
    for v in victims:
        c = v.get("color")
        if isinstance(c, str) and c in counts:
            counts[c] += 1
    return counts
