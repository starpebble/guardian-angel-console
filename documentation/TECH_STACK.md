# Guardian Angel Console — technical stack & integration

This document explains how **Firebase**, **Docker**, **FastAPI**, and the **web server (Uvicorn)** fit together in this repository. Product requirements and API contracts live in [`GUARDIAN_ANGEL_SPEC.md`](../GUARDIAN_ANGEL_SPEC.md); day-to-day setup is in [`developer.md`](../developer.md).

---

## 1. Big picture

```text
                    ┌─────────────────────────────────────────────┐
                    │              Docker image (optional)         │
                    │  CMD: uvicorn guardian_angel.main:app       │
                    │       --host 0.0.0.0 --port $PORT|…         │
                    └─────────────────────┬───────────────────────┘
                                          │
Browser / AI client ──HTTP──► FastAPI app (`guardian_angel.main:app`)
                                          │
                    ┌─────────────────────┴───────────────────────┐
                    │                                             │
              HTML + static                              JSON API
         (Jinja2 + `/static`)                         `/api/v1/*`
                    │                                             │
                    └─────────────────────┬───────────────────────┘
                                          │
                              Firestore (via Firebase Admin SDK)
                                          │
                                    Cloud Firestore
```

- **FastAPI** defines HTTP routes, request validation (Pydantic), OpenAPI, and dependencies (for example ingestion auth).
- **Uvicorn** is the **ASGI server** that runs the FastAPI application. Locally you start it explicitly; in Docker it is the container **CMD**.
- **Firebase** here means **Cloud Firestore** accessed through the **`firebase-admin`** Python library (initialized once, then `firestore.client()`).
- **Docker** packages the same Uvicorn + app process with locked dependencies (`uv.lock`) for repeatable deploys.

---

## 2. FastAPI — API surface and HTML console

| Layer | Role |
|--------|------|
| **`guardian_angel/main.py`** | Creates the FastAPI app, **lifespan** hook, mounts **`/static`**, registers **`guardian_angel.api.routes.v1`**, and defines **server-rendered pages** (`/`, `/transmissions`, `/medic-notes`) using **Jinja2** templates. |
| **`guardian_angel/api/routes/v1.py`** | Versioned JSON API under **`/api/v1`** (transmissions, victims, medic notes, meta). |
| **`guardian_angel/api/deps.py`** | Shared-secret checks for **POST** ingestion routes. |

**Why one process:** Operators hit **HTML pages** on the same origin as **`/api/v1/*`**, which keeps CORS simple and allows the backend to own all Firestore credentials (browser does not talk to Firebase directly in the current design).

---

## 3. Uvicorn — the web server

**Uvicorn** implements **HTTP → ASGI** for FastAPI.

| Environment | Typical command |
|---------------|-----------------|
| **Local dev** | `uv run uvicorn guardian_angel.main:app --reload --host 127.0.0.1 --port 8000` |
| **Docker / Cloud Run** | `uvicorn guardian_angel.main:app --host 0.0.0.0 --port "${PORT:-${GUARDIAN_ANGEL_PORT:-8000}}"` (see `Dockerfile`) |

**Port selection:** Cloud platforms often inject **`PORT`**. The image honors **`PORT`**, then **`GUARDIAN_ANGEL_PORT`**, then defaults to **8000**, matching the spec and `developer.md`.

**Concurrency note:** Firestore operations run in a **thread pool** (`run_in_threadpool`) from async route handlers so the event loop is not blocked on network I/O to Google APIs.

---

## 4. Firebase — Firestore via Firebase Admin

| Piece | Role |
|--------|------|
| **`firebase-admin`** | Initializes the Firebase app with either a **service account JSON file** or **Application Default Credentials** (GCP metadata, gcloud, etc.). |
| **`guardian_angel/services/firebase_client.py`** | **`get_firestore_client(project_id, service_account_path=...)`** — resolves credentials, calls **`firebase_admin.initialize_app`**, returns **`firestore.client()`**. |
| **`guardian_angel/services/firestore_store.py`** | All **writes and reads** for **`Transmissions`**, **`victims`**, **`stats/global`**, and the configurable **medic notes** collection. |

**Configuration (env):**

- **`FIREBASE_PROJECT_ID`** — if unset, the app runs **without** Firestore: UI uses **demo** victim data where applicable, and **POST** ingestion returns **503** (cannot persist).
- **`GOOGLE_APPLICATION_CREDENTIALS`** — path to service account JSON for local/dev containers; on GCP you may omit this and use workload identity / ADC instead.

**Data path:** AI pipeline → **`POST /api/v1/transmissions`** → Pydantic validation → **`FirestoreStore.ingest_transmission`** (transactional writes to victims + stats + transmission document). The console pages read back through the same store (or via **`GET /api/v1/*`** for JSON clients).

---

## 5. Docker — packaging the web server + app

The root **`Dockerfile`**:

1. Uses **`python:3.12-slim-bookworm`** and copies **`uv`** to install dependencies.
2. Copies **`pyproject.toml`**, **`uv.lock`**, and application code under **`guardian_angel/`**.
3. Runs **`uv sync --frozen --no-dev`** so production installs match the lockfile.
4. Runs as a **non-root** user **`app`**.
5. Exposes **8000** by default and defines a **`HEALTHCHECK`** against **`/health`** using the resolved port.
6. Starts **Uvicorn** bound to **`0.0.0.0`** so the container accepts external traffic (load balancer / `docker run -p`).

**Secrets:** API secret and Firebase settings are **runtime environment variables** (or secret mounts), not baked into image layers—see **`GUARDIAN_ANGEL_SPEC.md`** §8 and **`developer.md`**.

---

## 6. Request flow examples

### 6.1 Ingestion (AI → API → Firestore)

1. Client **`POST /api/v1/transmissions`** with JSON body and **`Authorization: Bearer …`** or **`X-Guardian-Angel-Token`**.
2. FastAPI parses body → **`TransmissionPayload`** (unknown fields preserved for storage).
3. Dependency **`require_ingestion_secret`** validates the shared secret (or returns **503** if the server has no secret configured).
4. Route handler calls **`FirestoreStore.ingest_transmission`** in a worker thread; Firestore transaction updates aggregates and documents.
5. Response **201** with **`transmission_id`**.

### 6.2 Operator browser → HTML console

1. **`GET /`** loads victims and counts: Firestore **`stats/global`** + **`victims`** (or demo data if Firestore is absent).
2. **`GET /transmissions`** and **`GET /medic-notes`** load recent rows from Firestore for tables; picture hex in payloads is turned into **data URIs** for inline preview where possible.

---

## 7. Related files

| File / directory | Purpose |
|------------------|---------|
| `Dockerfile` | Production-style image + Uvicorn CMD |
| `pyproject.toml` / `uv.lock` | Dependencies (FastAPI, Uvicorn, firebase-admin, Pydantic, …) |
| `guardian_angel/main.py` | ASGI app, static files, HTML routes |
| `guardian_angel/api/routes/v1.py` | JSON API |
| `guardian_angel/services/firebase_client.py` | Firebase Admin bootstrap |
| `guardian_angel/services/firestore_store.py` | Persistence layer |

For environment variables and Firebase console setup, use **`developer.md`**.
