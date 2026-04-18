"""Guardian Angel FastAPI application entrypoint."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.templating import Jinja2Templates

from guardian_angel import __version__
from guardian_angel.api.routes import v1 as v1_routes
from guardian_angel.config import Settings, get_settings
from guardian_angel.demo_data import aggregate_counts, demo_victims
from guardian_angel.hex_image import hex_to_image_data_uri
from guardian_angel.services.firebase_client import get_firestore_client
from guardian_angel.services.firestore_store import FirestoreStore
from guardian_angel.triage import TRIAGE_COLOR_ORDER, TRIAGE_LABELS

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings.cache_clear()
    settings = get_settings()
    app.state.settings = settings
    store: FirestoreStore | None = None
    if settings.firebase_project_id:
        try:
            client = get_firestore_client(
                settings.firebase_project_id,
                service_account_path=settings.google_application_credentials,
            )
            store = FirestoreStore(
                client,
                medic_notes_collection=settings.medic_notes_collection,
            )
            logger.info("Firestore store ready for project %s", settings.firebase_project_id)
        except Exception:
            logger.exception(
                "Firestore initialization failed; set FIREBASE_PROJECT_ID only when credentials are available. "
                "Running without Firestore (demo UI)."
            )
    else:
        logger.warning("FIREBASE_PROJECT_ID not set; using demo data for web UI and empty API reads.")
    app.state.store = store
    yield


app = FastAPI(
    title="Guardian Angel",
    version=__version__ if __version__ else "0.1.0",
    description="Incident command console and triage ingestion API",
    lifespan=lifespan,
)

app.include_router(v1_routes.router)

app.mount(
    "/static",
    StaticFiles(directory=str(_PACKAGE_DIR / "static")),
    name="static",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "guardian-angel"}


def _victim_rows_for_template(rows: list[dict]) -> list[dict[str, str | None]]:
    out: list[dict[str, str | None]] = []
    for r in rows:
        pref = r.get("picture_ref")
        pref_s = pref if isinstance(pref, str) else None
        picture_data_uri = hex_to_image_data_uri(pref_s) if pref_s else None
        # Demo rows use short placeholders; avoid dumping multi‑KB hex in the UI if decode fails.
        picture_text_fallback: str | None = None
        if picture_data_uri is None and pref_s:
            picture_text_fallback = pref_s if len(pref_s) <= 96 else None

        out.append(
            {
                "id": str(r.get("victim_id") or r.get("id", "")),
                "color": str(r.get("color", "")),
                "description": r.get("description"),
                "geo": r.get("geo"),
                "picture_ref": pref_s,
                "picture_data_uri": picture_data_uri,
                "picture_text_fallback": picture_text_fallback,
            }
        )
    return out


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    store: FirestoreStore | None = getattr(request.app.state, "store", None)
    if store is not None:

        def _load() -> tuple[dict, list[dict]]:
            return store.get_stats(), store.list_victims()

        try:
            stats, raw = await run_in_threadpool(_load)
            victims = _victim_rows_for_template(raw)
            counts = stats["by_color"]
            total = int(stats["total"])
        except Exception:
            logger.exception("Failed to load console data from Firestore; falling back to demo")
            victims = _victim_rows_for_template(demo_victims())
            counts = aggregate_counts(victims)
            total = len(victims)
    else:
        victims = _victim_rows_for_template(demo_victims())
        counts = aggregate_counts(victims)
        total = len(victims)

    return _TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "page_title": "Guardian Angel",
            "triage_system": settings.triage_system_label,
            "total_victims": total,
            "counts_by_color": counts,
            "triage_color_order": TRIAGE_COLOR_ORDER,
            "triage_labels": TRIAGE_LABELS,
            "victims": victims,
            "data_source": "firestore" if store else "demo",
        },
    )


@app.get("/transmissions", response_class=HTMLResponse)
async def transmissions_page(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    store: FirestoreStore | None = getattr(request.app.state, "store", None)
    rows: list[dict] = []
    if store is not None:

        def _load() -> list[dict]:
            items, _ = store.list_transmissions(limit=100, cursor=None)
            return items

        try:
            raw_rows = await run_in_threadpool(_load)
            rows = []
            for r in raw_rows:
                payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
                rows.append(
                    {
                        **r,
                        "payload_json": json.dumps(payload, indent=2, ensure_ascii=False),
                        "image_data_uri": hex_to_image_data_uri(
                            payload.get("picture") if isinstance(payload, dict) else None
                        ),
                    }
                )
        except Exception:
            logger.exception("Failed to load transmissions for page")
            rows = []
    return _TEMPLATES.TemplateResponse(
        request,
        "transmissions.html",
        {
            "page_title": "Transmissions",
            "triage_system": settings.triage_system_label,
            "rows": rows,
            "data_source": "firestore" if store else "none",
        },
    )


@app.get("/medic-notes", response_class=HTMLResponse)
async def medic_notes_page(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    store: FirestoreStore | None = getattr(request.app.state, "store", None)
    rows: list[dict] = []
    if store is not None:

        def _load() -> list[dict]:
            items, _ = store.list_medic_notes(limit=200, cursor=None)
            return items

        try:
            rows = await run_in_threadpool(_load)
        except Exception:
            logger.exception("Failed to load medic notes for page")
            rows = []
    return _TEMPLATES.TemplateResponse(
        request,
        "medic_notes.html",
        {
            "page_title": "Medic Notes",
            "triage_system": settings.triage_system_label,
            "rows": rows,
            "data_source": "firestore" if store else "none",
            "medic_notes_collection": settings.medic_notes_collection,
        },
    )
