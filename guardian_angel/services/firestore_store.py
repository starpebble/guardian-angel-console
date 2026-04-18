"""Firestore persistence (GUARDIAN_ANGEL_SPEC.md §9)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from guardian_angel.models.transmission import TransmissionPayload
from guardian_angel.triage import TRIAGE_COLOR_ORDER

logger = logging.getLogger(__name__)

# Match Firebase console collection name (case-sensitive).
COLLECTION_TRANSMISSIONS = "Transmissions"

SERVER_TIMESTAMP = firestore.SERVER_TIMESTAMP


def _dt_from_firestore(ts: Any) -> datetime | None:
    if ts is None:
        return None
    if hasattr(ts, "timestamp"):
        return datetime.fromtimestamp(ts.timestamp(), tz=timezone.utc)
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return None


class FirestoreStore:
    """Collections: ``Transmissions``, ``victims``, ``stats/global``, medic notes collection (configurable)."""

    def __init__(
        self,
        db: firestore.Client,
        *,
        medic_notes_collection: str = "Medic Notes",
    ) -> None:
        self._db = db
        self._medic_notes_collection = medic_notes_collection

    def ingest_transmission(self, payload: TransmissionPayload) -> str:
        transmission_id = str(uuid.uuid4())
        stored_payload = payload.to_stored_dict()

        @firestore.transactional
        def _commit(tx: firestore.Transaction) -> None:
            # Firestore: all transactional reads must complete before any write.
            stats_ref = self._db.collection("stats").document("global")
            stats_snap = stats_ref.get(transaction=tx)
            by_color: dict[str, int] = {c: 0 for c in TRIAGE_COLOR_ORDER}
            total = 0
            if stats_snap.exists:
                data = stats_snap.to_dict() or {}
                total = int(data.get("total", 0))
                existing = data.get("by_color") or {}
                for c in TRIAGE_COLOR_ORDER:
                    by_color[c] = int(existing.get(c, 0))

            geo = payload.geo
            picture = payload.picture

            unique_vids = list(dict.fromkeys(e.id for e in payload.triage))
            prev_by_vid: dict[str, Any] = {}
            for vid in unique_vids:
                vref = self._db.collection("victims").document(vid)
                prev_by_vid[vid] = vref.get(transaction=tx)

            # Stats: apply triage rows in order; duplicate victim ids use rolling color within payload.
            rolled_color: dict[str, str] = {}
            for entry in payload.triage:
                vid = entry.id
                new_color = entry.color.value
                if vid not in rolled_color:
                    ps = prev_by_vid[vid]
                    new_doc = not ps.exists
                    old_color = (ps.to_dict() or {}).get("color") if ps.exists else None
                else:
                    new_doc = False
                    old_color = rolled_color[vid]

                if new_doc:
                    total += 1
                    by_color[new_color] = by_color.get(new_color, 0) + 1
                elif old_color != new_color:
                    if old_color in by_color:
                        by_color[old_color] = max(0, by_color[old_color] - 1)
                    by_color[new_color] = by_color.get(new_color, 0) + 1

                rolled_color[vid] = new_color

            for entry in payload.triage:
                vid = entry.id
                vref = self._db.collection("victims").document(vid)
                new_color = entry.color.value
                tx.set(
                    vref,
                    {
                        "victim_id": vid,
                        "color": new_color,
                        "description": entry.description,
                        "geo": geo,
                        "picture_ref": picture,
                        "last_transmission_id": transmission_id,
                        "updated_at": SERVER_TIMESTAMP,
                    },
                    merge=True,
                )

            tx.set(
                stats_ref,
                {"total": total, "by_color": by_color, "updated_at": SERVER_TIMESTAMP},
                merge=True,
            )

            tx.set(
                self._db.collection(COLLECTION_TRANSMISSIONS).document(transmission_id),
                {
                    "transmission_id": transmission_id,
                    "received_at": SERVER_TIMESTAMP,
                    "payload": stored_payload,
                },
                merge=True,
            )

        _commit(self._db.transaction())
        logger.info("Stored transmission %s (%d triage rows)", transmission_id, len(payload.triage))
        return transmission_id

    def get_stats(self) -> dict[str, Any]:
        snap = self._db.collection("stats").document("global").get()
        if not snap.exists:
            return {
                "total": 0,
                "by_color": {c: 0 for c in TRIAGE_COLOR_ORDER},
            }
        d = snap.to_dict() or {}
        by_color = {c: int((d.get("by_color") or {}).get(c, 0)) for c in TRIAGE_COLOR_ORDER}
        return {"total": int(d.get("total", 0)), "by_color": by_color}

    def list_victims(self, limit: int = 500) -> list[dict[str, Any]]:
        q = self._db.collection("victims").order_by(
            "updated_at", direction=firestore.Query.DESCENDING
        )
        out: list[dict[str, Any]] = []
        for doc in q.limit(limit).stream():
            row = doc.to_dict() or {}
            row.setdefault("id", doc.id)
            ts = row.get("updated_at")
            row["_updated_at"] = _dt_from_firestore(ts)
            out.append(row)
        return out

    def list_transmissions(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        col = self._db.collection(COLLECTION_TRANSMISSIONS)
        q = col.order_by("received_at", direction=firestore.Query.DESCENDING)
        if cursor:
            cur = col.document(cursor).get()
            if cur.exists:
                q = q.start_after(cur)
        snaps = list(q.limit(limit + 1).stream())
        has_more = len(snaps) > limit
        page = snaps[:limit]
        items: list[dict[str, Any]] = []
        for doc in page:
            d = doc.to_dict() or {}
            payload = d.get("payload")
            if not payload and isinstance(d, dict) and (
                "boundingbox" in d or "bounding_box" in d or d.get("id") is not None
            ):
                # Legacy / hand-authored docs: triage-like fields at document root (see console mocks).
                bbox = d.get("boundingbox") if isinstance(d.get("boundingbox"), dict) else d.get("bounding_box")
                payload = {
                    "triage_system": "SALT",
                    "triage": [
                        {
                            "id": d.get("id") or "",
                            "color": d.get("color") or "gray",
                            "boundingbox": bbox or {},
                            "description": d.get("description") or "",
                        }
                    ],
                }
            if not isinstance(payload, dict):
                payload = {}
            received = d.get("received_at")
            triage = payload.get("triage") if isinstance(payload, dict) else []
            victim_count = len(triage) if isinstance(triage, list) else 0
            items.append(
                {
                    "transmission_id": d.get("transmission_id", doc.id),
                    "received_at": _dt_from_firestore(received),
                    "geo": payload.get("geo") if isinstance(payload, dict) else None,
                    "triage_system": (
                        (payload.get("triage_system") or payload.get("triage-system"))
                        if isinstance(payload, dict)
                        else None
                    ),
                    "victim_count": victim_count,
                    "payload": payload,
                }
            )
        next_cursor: str | None = None
        if has_more and page:
            next_cursor = page[-1].id
        return items, next_cursor

    def add_medic_note(self, notes: str) -> str:
        """Append one document with string field ``notes`` and ``created_at``."""

        doc_id = str(uuid.uuid4())
        ref = self._db.collection(self._medic_notes_collection).document(doc_id)
        ref.set(
            {
                "notes": notes,
                "created_at": SERVER_TIMESTAMP,
            }
        )
        logger.info("Stored medic note %s in %s", doc_id, self._medic_notes_collection)
        return doc_id

    def list_medic_notes(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        col = self._db.collection(self._medic_notes_collection)
        q = col.order_by("created_at", direction=firestore.Query.DESCENDING)
        if cursor:
            cur = col.document(cursor).get()
            if cur.exists:
                q = q.start_after(cur)
        snaps = list(q.limit(limit + 1).stream())
        has_more = len(snaps) > limit
        page = snaps[:limit]
        items: list[dict[str, Any]] = []
        for doc in page:
            d = doc.to_dict() or {}
            items.append(
                {
                    "id": doc.id,
                    "notes": str(d.get("notes", "")),
                    "created_at": _dt_from_firestore(d.get("created_at")),
                }
            )
        next_cursor: str | None = None
        if has_more and page:
            next_cursor = page[-1].id
        return items, next_cursor
