# Guardian Angel — Product & Technical Specification

**Version:** 0.4 (draft for iteration)  
**Last updated:** 2026-04-18  
**Stack:** Python **FastAPI** (HTTP APIs + Jinja2 HTML UI), **Uvicorn** (ASGI web server), **Firebase Admin** → **Cloud Firestore** (persistence), **Docker** (deployment)

This document is the single source of truth for **Guardian Angel**, a local-first web console for **incident command** and **military medic / responder** workflows during mass-casualty events. It ingests structured transmissions from an external AI triage application and presents operational situational awareness: aggregate victim counts and per-victim detail with filtering.

**Companion:** For how FastAPI, Uvicorn, Firestore, and Docker connect at runtime, see [`documentation/TECH_STACK.md`](documentation/TECH_STACK.md).

---

## 1. Purpose & users

| Goal | Description |
|------|-------------|
| **Situational awareness** | Show how many victims have been reported and their triage disposition. |
| **Ingestion** | Accept high-frequency JSON payloads from an AI app that triages scene imagery or sensor data. |
| **Persistence** | Store every accepted transmission and derived victim records in **Firebase** so multiple operators can share state (and for audit/replay). |
| **Operations** | Run **locally** on a laptop or tablet on-scene; package as a **Docker** image for cloud or edge deployment. |

**Primary users:** incident commanders, senior medics, and comms staff coordinating a multi-victim response.

---

## 2. Naming & branding

- **Product name:** Guardian Angel  
- **Suggested short code / image name:** `guardian-angel` (lowercase, hyphenated for containers and packages)

---

## 3. High-level architecture

```
┌─────────────────┐     HTTPS/JSON      ┌──────────────────────┐
│  AI triage app  │ ──────────────────► │  Guardian Angel API   │
└─────────────────┘                     │  (Python)             │
                                        │  • validate (Pydantic)│
                                        │  • auth (shared secret) │
                                        └──────────┬───────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
            ┌───────────────┐              ┌───────────────┐              ┌───────────────┐
            │   Firebase    │              │  Web console  │              │  (optional)   │
            │  Firestore or │◄─────────────│  HTML/JS UI   │              │  future APIs  │
            │  Realtime DB  │   read path  │  two-pane UI  │              │               │
            └───────────────┘              └───────────────┘              └───────────────┘
```

- **Backend:** **FastAPI** + **Uvicorn** — REST API (`/api/v1/*`), Pydantic models, **Jinja2** server-rendered pages, static assets under `/static`.  
- **Front-end:** Browser UI served by the **same ASGI process** as the API (spec assumes **one deployment unit** unless split later).  
- **Firebase:** **Cloud Firestore** via **`firebase-admin`** (Python) — persist payloads and normalized victim rows; optional future: Firestore listeners or WebSockets for sub-second UI (see §13).

### 3.1 Runtime modes (as implemented)

| Mode | When | Operator UI | `POST /api/v1/transmissions` / `POST /api/v1/medicnotes` |
|------|------|-------------|----------------------------------------------------------|
| **Connected** | `FIREBASE_PROJECT_ID` set and Firebase Admin / Firestore client initializes | Main `/` reads **`stats/global`** + **`victims`**; `/transmissions` and `/medic-notes` read Firestore | **201** on success |
| **No database** | `FIREBASE_PROJECT_ID` unset, credentials missing/invalid, or init raises | Main `/` uses **demo** victim data; log pages show **no rows** (`data_source` indicates none) | **503** — cannot persist |
| **Secret missing** | Ingestion secret env not set | Same as row above for reads | **503** — ingestion disabled (misconfiguration), not **401** |

Firestore client calls run off the asyncio event loop (thread pool) so ingestion stays responsive under bursty writes.

---

## 4. Functional requirements

### 4.1 Ingestion API

- **Endpoint:** `POST /api/v1/transmissions` (version prefix allows breaking changes without colliding with the console).  
- **Body:** JSON matching an **evolving Pydantic schema** (see §6).  
- **Behavior:**  
  - Validate payload.  
  - On success: write to Firestore (raw payload + denormalized victim records + aggregate stats in a transaction — see §9).  
  - Return **`201 Created`** with a server-generated `transmission_id`. If Firestore is not available, return **`503 Service Unavailable`** with an explicit error detail.  
- **Idempotency (optional v1):** consider `Idempotency-Key` header for retries; document when implemented.

- **Medic notes ingestion:** `POST /api/v1/medicnotes` with body `{ "notes": "<string>" }`, same authentication as transmissions — see §4.4.

### 4.2 Console UI — main page (two panes)

| Pane | Content | Behavior |
|------|---------|----------|
| **Pane A — Victim count** | Total victims reported; optional breakdown by **SALT triage color** | Aggregated from stored victim records (or from latest transmission summaries — product decision: prefer **authoritative aggregate in Firebase** updated on each write). |
| **Pane B — Victim list** | Rows keyed by victim id, with color, short description, geo reference (if any), link or thumbnail reference to picture | **Filter** by triage **color** (and optionally text search on `id` / `description` in later iterations). |
| **SALT & five colors** | Align with the SALT triage color set used by the AI pipeline | Standard five-color set for this project (canonical enum in code — see §6.2). |

**Visual theme — dark:** The console **defaults to a dark theme** (dark background, light text) for low-light operations and reduced glare on-scene. Triage color badges and indicators MUST remain distinguishable and meet readable contrast against the dark surfaces (WCAG AA for text where feasible; at minimum, do not rely on color alone for status). A light theme is optional in a later iteration; v1 ships **dark-only** unless product requests a toggle.

### 4.3 Console UI — transmissions log page

A **separate web page** (e.g. route `/transmissions`, linked from the main console navigation) dedicated to the **complete ingestion history** mirrored in Firebase.

| Aspect | Requirement |
|--------|----------------|
| **Data source** | Every successful `POST /api/v1/transmissions` record persisted under **`Transmissions/{id}`** (Firestore collection id, see §9): stored **raw JSON body** (or equivalent), `received_at`, and `transmission_id`. |
| **Layout — columnar** | Present each transmission as a **row** in a **table** (columnar layout): columns SHOULD include at minimum `transmission_id`, `received_at`, **`geo`** (if present), **`triage_system`** (if present), victim count / summary, and a **formatted view of the full JSON** (e.g. syntax-highlighted, expandable cell, or side panel — implementer’s choice, but operators must be able to inspect the **entire** message as received). |
| **Photo** | The payload’s **`picture`** field (e.g. hex-encoded image bytes from the AI app) MUST be **decodable and viewable** on this page: show an **inline thumbnail and/or full-size preview** per row or in a detail drawer when a row is selected. If decoding fails, show a clear error state (not a silent blank). |
| **Ordering** | Default sort: **newest first** (`received_at` descending). |
| **Theme** | Same **dark theme** and readability expectations as §4.2. |

**Supporting API (recommended):** Expose **`GET /api/v1/transmissions`** with pagination (`limit`, optional `cursor` — document id of the last row from the previous page) so clients can load history without direct browser access to Firebase credentials; the server-rendered **`/transmissions`** page uses the same store with a **fixed recent window** (implementation loads up to **100** rows; use the JSON API for deeper history).

### 4.4 Medic notes API & console page

**Ingestion API**

- **Endpoint:** `POST /api/v1/medicnotes`  
- **Body:** JSON with a single string field **`notes`** (non-empty).  
- **Auth:** Same **shared secret** as triage ingestion — `Authorization: Bearer <secret>` or `X-Guardian-Angel-Token` (see §7).  
- **Behavior:** Append one Firestore document to the **medic notes** collection (default name **`Medic Notes`**; configurable via environment so it matches the Firebase console). Store **`notes`** plus server **`created_at`**. Return **201** with a server-generated **`note_id`**.

**Read API (optional for clients)**

- **`GET /api/v1/medicnotes`** — paginated list (`limit`, `cursor`), newest first by `created_at`. Unauthenticated for v1 (same pattern as **`GET /api/v1/victims`**); the browser console loads via server-rendered HTML.

**Console UI**

- **Route:** e.g. **`/medic-notes`** — **Medic Notes** page linked from the main console navigation.  
- **Content:** Table of medic notes (timestamp, document id, text), **dark theme** consistent with §4.2–§4.3.

### 4.5 Health & metadata

- `GET /health` — liveness (200 + minimal JSON).  
- `GET /api/v1/meta` — JSON including: application **version**, **`triage_system`** label (e.g. `SALT`), optional **`git_sha`** (from `GIT_SHA` at build/deploy time), and **`firestore`** (boolean — whether this process successfully initialized a Firestore-backed store).

---

## 5. Non-functional requirements

| Area | Requirement |
|------|-------------|
| **Performance** | Ingestion path optimized for bursty traffic; avoid blocking the event loop on Firebase writes (async client or thread pool). |
| **Security** | No anonymous ingestion: **shared secret** (symmetric) — see §7. |
| **Config** | All secrets and Firebase keys via **environment variables** loaded from a **`.env` file** in development (see §8). Never commit `.env`. |
| **Observability** | Structured logs; log transmission id and error reason on reject. |
| **UX / display** | **Dark theme** by default for the web console (see §4.2–§4.4); suitable for field use in varied lighting. |

---

## 6. Data model & API contract

### 6.1 Evolution strategy (payloads change often)

- **Pydantic v2** models with **explicit optional fields** and a **`extra` policy** decision:  
  - **Recommended:** `model_config = ConfigDict(extra="allow")` on a top-level `TransmissionPayload` (or nested dict) so unknown fields are preserved in Firebase without crashing the API.  
  - **Version field:** optional `schema_version: str | int` on the payload for forward compatibility.  
- **Breaking changes:** bump path to `/api/v2/...` or use explicit version inside JSON plus separate Pydantic classes per version.

### 6.2 Canonical triage colors (five)

Use a single **enum** in application code and document it here. Example mapping (adjust to match your AI/training doctrine):

| Enum value | Typical SALT/MCI meaning |
|------------|---------------------------|
| `red` | Immediate |
| `yellow` | Delayed |
| `green` | Minimal / walking wounded |
| `gray` | Ambiguous / needs re-triage |
| `black` | Expectant / deceased |

*If your operational orders use different labels, change the enum **values** but keep **five** discrete colors for filtering.*

### 6.3 Example JSON payload (illustrative)

Field names use **snake_case** in the canonical API (Pydantic aliases can accept `triage-system` from clients — see note below).

```json
{
  "picture": "656e636f6465642d686578",
  "geo": "37.7749 -122.4194",
  "triage_system": "SALT",
  "triage": [
    {
      "id": "T1V1",
      "color": "red",
      "bounding_box": {
        "width": 70,
        "height": 166,
        "x": 646,
        "y": 317
      },
      "description": "bleeding and impaled in leg"
    },
    {
      "id": "T1V2",
      "color": "green",
      "bounding_box": {
        "width": 80,
        "height": 100,
        "x": 200,
        "y": 200
      },
      "description": "laying on ground, awake, breathing, no blood"
    }
  ]
}
```

**Interoperability note:** External AI apps may send **kebab-case** keys (e.g. `triage-system`, `boundingbox`). The implementation SHOULD use Pydantic **field aliases** and **`populate_by_name=True`** so both `triage_system` and `triage-system` deserialize to the same field.

### 6.4 Pydantic shapes (reference)

*Exact names may be refined in implementation; this is the intended structure.*

```text
TransmissionPayload
  picture: str | None          # hex-encoded image or reference string from AI
  geo: str | None               # free-form "lat long" or WKT later
  triage_system: str | None    # e.g. "SALT"
  triage: list[VictimTriageEntry]

VictimTriageEntry
  id: str
  color: TriageColor            # enum: red | yellow | green | gray | black
  bounding_box: BoundingBox | None
  description: str | None

BoundingBox
  width: float | int
  height: float | int
  x: float | int
  y: float | int
```

---

## 7. Security: symmetric shared secret

**Model:** A single **pre-shared key** (long random string) known to the AI pipeline and the Guardian Angel deployment.

| Aspect | Specification |
|--------|-----------------|
| **Env var** | `GUARDIAN_ANGEL_API_SECRET` (or `GUARDIAN_ANGEL_SHARED_SECRET`) |
| **Client sends** | Header: `Authorization: Bearer <secret>` **or** `X-Guardian-Angel-Token: <secret>` (both supported; see OpenAPI). Same secret protects **`POST /api/v1/transmissions`** and **`POST /api/v1/medicnotes`**. |
| **Server** | **Constant-time** comparison of credentials (implementation compares **SHA-256 digests** with `hmac.compare_digest` so timing does not leak key length). Reject with **401** if missing/invalid when a secret **is** configured. If **no** secret is configured, ingestion endpoints return **503** (misconfiguration). |
| **Rotation** | Document process: deploy new secret, update AI app, retire old (optional dual-secret window in future). |

*This is minimal operational security suitable for controlled networks; it is **not** a substitute for TLS in production — always terminate TLS at the load balancer or reverse proxy.*

---

## 8. Configuration & `.env`

All configuration via environment variables. **Development:** use a `.env` file at the project root (loaded by `python-dotenv` or Docker Compose `env_file`). **Production:** inject via orchestrator secrets.

### 8.1 Required / expected variables

| Variable | Purpose |
|----------|---------|
| `GUARDIAN_ANGEL_API_SECRET` | Shared secret for API authentication (alias: `GUARDIAN_ANGEL_SHARED_SECRET` — either may be set) |
| `FIREBASE_PROJECT_ID` | GCP / Firebase project id |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON (local / VM) **or** use workload identity in GKE/Cloud Run |
| `GUARDIAN_ANGEL_MEDIC_NOTES_COLLECTION` | Optional — Firestore collection id for medic notes (default **`Medic Notes`**) |
| `GUARDIAN_ANGEL_HOST` | Bind address (default `0.0.0.0` in container) |
| `GUARDIAN_ANGEL_PORT` | Listen port (default `8000`; Docker/Cloud Run often use `PORT`) |
| `GIT_SHA` | Optional — surfaced in **`GET /api/v1/meta`** for deploy traceability |

### 8.2 `.env.example` (committed)

Duplicate this section as a real `.env.example` file when implementing (values fake):

```dotenv
# Guardian Angel — example environment (copy to .env and fill in)

GUARDIAN_ANGEL_API_SECRET=change-me-to-a-long-random-string
FIREBASE_PROJECT_ID=your-firebase-project
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

GUARDIAN_ANGEL_HOST=0.0.0.0
GUARDIAN_ANGEL_PORT=8000
```

---

## 9. Firebase data layout (recommended)

*Exact collection names are implementation details; suggested structure:*

| Collection / path | Contents |
|-------------------|----------|
| `Transmissions/{id}` | Raw payload JSON, `received_at` timestamp, `transmission_id` (collection name matches Firebase console) |
| `victims/{victim_id}` | Latest known state for that id, `color`, `description`, `last_transmission_id`, `geo` snapshot |
| `{MedicNotesCollection}/{id}` | String field **`notes`**, **`created_at`** — collection id configurable (default **`Medic Notes`**, see §8) |

**Aggregates:** Maintain `stats/global` document with counts by color and total, updated in a transaction or batched write on each ingestion to keep Pane A O(1) read.

**Rules:** Lock down client writes; **only** the Guardian Angel backend uses the service account with write access. Browser reads via Firebase SDK require **security rules** that allow read-only to authenticated operators *or* proxy all reads through the Python server (simpler for v1: **server-side only Firebase access**, UI uses REST **`GET /api/v1/victims`** for the main list, **`GET /api/v1/transmissions`** for the transmissions log, and **`GET /api/v1/medicnotes`** for medic notes — see §4.3–§4.4).

**SDK:** The reference implementation uses **`firebase-admin`** to obtain a **`google.cloud.firestore.Client`** for the configured GCP project (service account JSON or Application Default Credentials).

---

## 10. Local development metadata

The repository includes:

| Artifact | Role |
|----------|------|
| `pyproject.toml` | Project **`guardian-angel`**, Python **≥ 3.12**, dependencies: **fastapi**, **uvicorn**, **jinja2**, **pydantic**, **pydantic-settings**, **python-dotenv**, **firebase-admin**, **httpx**, **pillow** (hex image preview) |
| `guardian_angel/` | Installable package: **`main.py`** (app + HTML routes), **`api/routes/v1.py`**, **`services/firestore_store.py`**, **`templates/`**, **`static/`** |
| `README.md` | Quickstart: `uv sync`, `uv run uvicorn …` |
| `uv.lock` | Locked dependency versions (generated by **`uv lock`**; commit to git) |
| **Run command (dev)** | `uv run uvicorn guardian_angel.main:app --reload --host 127.0.0.1 --port 8000` (after **`uv sync`**) |

**Local URL:** `http://127.0.0.1:8000/` (main console), `http://127.0.0.1:8000/transmissions` (transmissions log — §4.3), `http://127.0.0.1:8000/medic-notes` (medic notes — §4.4), and `http://127.0.0.1:8000/docs` (OpenAPI).

---

## 11. Docker & cloud deployment metadata

### 11.1 Container expectations

| Item | Specification |
|------|----------------|
| **Base image** | `python:3.12-slim` (or current stable slim) |
| **User** | Non-root user in final stage |
| **Port** | Expose `8000` (configurable via `GUARDIAN_ANGEL_PORT`) |
| **Config** | Env vars at runtime; **no** secrets baked into image |
| **Healthcheck** | `curl -f http://localhost:8000/health` or Python one-liner |

### 11.2 `Dockerfile` (repository)

The repo root **`Dockerfile`** builds a single image: **`python:3.12-slim-bookworm`**, **`uv sync --frozen --no-dev`** from **`uv.lock`**, non-root user **`app`**, **`HEALTHCHECK`** on **`/health`** (port from **`PORT`** / **`GUARDIAN_ANGEL_PORT`** / default **8000**), and **`CMD`** running **Uvicorn** on **`0.0.0.0`** with the same port resolution (see file comments).

### 11.3 Compose (optional)

- `docker-compose.yml` with `env_file: .env`, port mapping `8000:8000`, volume for `GOOGLE_APPLICATION_CREDENTIALS` if using a file mount locally.

### 11.4 Cloud notes

- **Cloud Run / ECS / Kubernetes:** pass secrets via secret manager; mount Firebase credentials as secret volume or use workload identity.  
- **CORS:** if the AI app posts from a different origin, configure FastAPI `CORSMiddleware` for known origins only.

---

## 12. OpenAPI & testing hooks

- Auto-generated **OpenAPI** at `/openapi.json`; keep Pydantic models as the single schema source.  
- **Contract tests:** golden JSON fixtures under `tests/fixtures/` including the example payload and variants with extra unknown fields.

---

## 13. Roadmap (out of scope for v0.1 unless pulled in)

- WebSocket or Firestore listeners for sub-second UI refresh  
- Operator authentication (OAuth / mutual TLS) beyond shared secret  
- Map view for `geo`  
- Export (CSV/PDF) for after-action review  

---

## 14. Glossary

| Term | Meaning |
|------|---------|
| **SALT** | Sort, Assess, Lifesaving interventions, Treatment/Triage — triage methodology; colors operationalize priority |
| **Transmission** | One POST body from the AI app, possibly containing multiple victims |
| **Victim entry** | One object in the `triage` array |

---

*End of specification — iterate by bumping **Version** and **Last updated** at the top.*
