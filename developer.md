# Guardian Angel — developer setup

This guide lists **everything you need to obtain, create, or configure** so the Guardian Angel app can run locally or in a container. Product behavior, APIs, and data models are defined in [`GUARDIAN_ANGEL_SPEC.md`](GUARDIAN_ANGEL_SPEC.md).

---

## 1. Prerequisites on your machine

| Requirement | Notes |
|---------------|--------|
| **Python** | **3.12.x** for this repo (see **`.python-version`**). **uv** downloads a compatible CPython when you use `uv sync` (see below). |
| **uv** | [uv](https://docs.astral.sh/uv/getting-started/installation/) manages the virtualenv and installs from **`pyproject.toml`** + **`uv.lock`**. |
| **Git** | To clone and update this repository. |
| **Docker** (optional) | For building and running the container described in spec §11. |

### 1.1 Virtual environment and dependencies (uv)

From the repository root:

```bash
uv sync
```

- **`uv sync`** creates **`.venv/`** if needed, resolves **`uv.lock`**, and installs **guardian-angel** in editable mode.
- After changing **`pyproject.toml`**, run **`uv lock`** (to refresh the lockfile) and **`uv sync`** again.
- **`uv run <command>`** runs a command inside the project environment without activating the venv (for example `uv run uvicorn guardian_angel.main:app --reload`).
- **`.python-version`** (3.12.12) is honored by uv when selecting the interpreter for the venv.
- **`.venv/`** is gitignored; each machine has its own.
- In **Cursor / VS Code**, choose the interpreter **`./.venv/bin/python`** (Command Palette → “Python: Select Interpreter”) so the environment stays active in the IDE.

---

## 2. What you must “give” the application

The app reads configuration from the **environment**. In development, put values in a **`.env` file** at the repository root (loaded via `python-dotenv` or Docker `env_file`). **Do not commit `.env`.**

### 2.1 API shared secret (symmetric)

- **Purpose:** Ingestion endpoints reject unauthenticated requests. Clients (e.g. the AI triage pipeline) send this value so the server can verify them.
- **You provide:** A long, random string stored as **`GUARDIAN_ANGEL_API_SECRET`** (see spec §7–§8).
- **How to generate one (example):**

  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- **Clients send it** as `Authorization: Bearer <secret>` or as agreed in the implemented API (see OpenAPI `/docs` when the app exists).

### 2.2 Firebase / Google Cloud

- **Purpose:** Persist transmissions, victim records, and aggregates (spec §9).
- **You provide:**
  - A **Firebase (GCP) project** — create one in the [Firebase console](https://console.firebase.google.com/) or use an existing project your team owns.
  - **`FIREBASE_PROJECT_ID`** — the project ID (often visible in Project settings).
  - **Credentials for the server** — one of:
    - **Service account JSON file** (typical for local dev): create a service account in Google Cloud IAM, grant roles needed for **Firestore** (and any other Firebase services the implementation uses), create a JSON key, download it, and set **`GOOGLE_APPLICATION_CREDENTIALS`** to the **absolute path** of that file; **or**
    - **Workload identity / metadata** in GCP (Cloud Run, GKE, etc.) so no JSON file is mounted — set up per your platform; omit or adjust `GOOGLE_APPLICATION_CREDENTIALS` per implementation docs.

**Firestore:** Guardian Angel persists data in **Cloud Firestore** (Native mode). Exact collections are in spec §9. See **§4** for how this fits the **current** Firebase console layout.

**Security:** Restrict who can access the service account key. Rotate keys if leaked. Production should use TLS in front of the app (spec §7).

### 2.3 Network binding (optional)

| Variable | Purpose |
|----------|---------|
| `GUARDIAN_ANGEL_HOST` | Bind address. Use `127.0.0.1` for local-only; `0.0.0.0` inside Docker. |
| `GUARDIAN_ANGEL_PORT` | Listen port (default **8000**). |

---

## 3. Create your `.env` file

1. Copy the example below to **`.env`** in the project root (create `.env.example` in the repo when the app is scaffolded and copy from that instead).

2. Replace every placeholder with real values.

```dotenv
# Guardian Angel — local development (do not commit)

# Required: long random string (see §2.1)
GUARDIAN_ANGEL_API_SECRET=change-me-to-a-long-random-string

# Required: Firebase project
FIREBASE_PROJECT_ID=your-firebase-project

# Required for local dev with a key file: absolute path to service account JSON
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json

# Optional
GUARDIAN_ANGEL_HOST=127.0.0.1
GUARDIAN_ANGEL_PORT=8000
```

3. Confirm **`.env`** is listed in **`.gitignore`** once the project adds one.

---

## 4. Firebase database setup (current console)

The Firebase console **Build** area now groups database products under **Databases and storage** (in Spanish: *Bases de datos y almacenamiento*; wording and placement can vary by locale and UI version). The important point is that **several database types** are offered; Guardian Angel uses **only one** of them.

### 4.1 Which product to use for Guardian Angel

| Option (typical console grouping) | Use for this app? | Notes |
|-----------------------------------|-------------------|--------|
| **Firestore** (under **NoSQL**) | **Yes** | This is what the Python backend uses via `firebase-admin` / the Firestore API. Create the database in **Native mode** when prompted. |
| **Realtime Database** (NoSQL, JSON tree) | **No** | A different product and SDK. The codebase does **not** read or write the Realtime Database. |
| **Data Connect** / **PostgreSQL** (sometimes labeled **NEW**) | **No** | Managed SQL + GraphQL. Not used by this project. |
| **Storage** (object / file storage) | **Optional** | Guardian Angel can store scene data as hex/strings in Firestore payloads; you can add Storage later if you want large blobs in GCS instead. |

If you already created the wrong product, you can still add **Firestore** in the same Firebase project; just ensure **`FIREBASE_PROJECT_ID`** matches that project and that Firestore is provisioned.

### 4.2 Enable Firestore (Native mode)

1. Open the [Firebase console](https://console.firebase.google.com/) and select your project.
2. In the left navigation, open **Build** → **Databases and storage** (or **Build** → **Firestore Database**, depending on UI version).
3. Choose **Cloud Firestore** / **Firestore** (not Realtime Database, not Data Connect).
4. When creating the database, pick a **location** (region) for the data; this cannot be changed later for that database.
5. Start in **production** mode or **test** mode according to your policy. The backend uses the **Admin SDK** with a service account, so **client-facing security rules** do not apply to server writes; you should still deploy sensible rules before any direct browser access to Firestore.

### 4.3 Service account and local credentials

After Firestore exists in the project:

1. In Google Cloud **IAM & Admin** → **Service accounts** (same project as Firebase), create or select a service account used by this app.
2. Grant it a role that allows Firestore access (for example **Cloud Datastore User** (`roles/datastore.user`) or a tighter custom role).
3. Create a **JSON key**, download it, and set **`GOOGLE_APPLICATION_CREDENTIALS`** in **`.env`** to the **absolute path** of that file (see §3).
4. Set **`FIREBASE_PROJECT_ID`** to the Firebase / GCP **project ID** (Project settings).

### 4.4 Quick checklist

1. Project created; **Project ID** copied → `FIREBASE_PROJECT_ID`.
2. **Firestore** (Native) enabled — not Realtime Database, not Data Connect.
3. Service account + JSON key; path in **`GOOGLE_APPLICATION_CREDENTIALS`**.
4. First run: confirm logs show Firestore initialization (not “demo data only”).
5. The app persists API transmissions to the Firestore collection **`Transmissions`** (capital **T**, case-sensitive). Hand-created test documents with a different field layout may still appear on the transmissions page (see app logic); delete them if you want only API-shaped rows.

### 4.5 Load mock data via the API

From the repo root (server running, `.env` with **`GUARDIAN_ANGEL_API_SECRET`**):

```bash
uv run python test-data.py
```

This posts **five** transmissions—one per row from **`guardian_angel.demo_data.demo_victims()`**—so the UI matches the built-in demo (including per-victim **geo** and **picture** fields). After wiring to Firestore, victim and aggregate counts are **zero** until you ingest data (or they reflect what is already in **`victims`** and **`stats/global`**). Remove stray manual documents in **`Transmissions`** if you expect an empty log before the first real ingest.

---

## 5. Run the application (after implementation exists)

Once the repository includes installable code (`pyproject.toml`, package `guardian_angel`, etc.):

1. Run **`uv sync`** so the environment matches **`uv.lock`**.

2. Start the server (from spec §10), either with **`uv run`** or after **`source .venv/bin/activate`**:

   ```bash
   uv run uvicorn guardian_angel.main:app --reload --host 127.0.0.1 --port 8000
   ```

3. Open:

   | URL | Purpose |
   |-----|---------|
   | `http://127.0.0.1:8000/` | Main console |
   | `http://127.0.0.1:8000/transmissions` | Transmissions log (spec §4.3) |
   | `http://127.0.0.1:8000/medic-notes` | Medic notes (spec §4.4) |
   | `http://127.0.0.1:8000/docs` | OpenAPI / Swagger |
   | `http://127.0.0.1:8000/health` | Liveness |

If these routes are missing, the app is not fully implemented yet — use the spec and issue tracker for status.

---

## 6. Verify the ingestion API

When `POST /api/v1/transmissions` exists, test with a Bearer token matching `GUARDIAN_ANGEL_API_SECRET`:

```bash
export GUARDIAN_ANGEL_API_SECRET='your-secret-from-env'
curl -sS -X POST "http://127.0.0.1:8000/api/v1/transmissions" \
  -H "Authorization: Bearer $GUARDIAN_ANGEL_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"triage_system":"SALT","triage":[]}'
```

Adjust the JSON body to match [`GUARDIAN_ANGEL_SPEC.md`](GUARDIAN_ANGEL_SPEC.md) §6. Expect **401** if the secret is wrong or missing.

---

## 7. Docker

1. From the repo root: **`docker build -t guardian-angel .`**
2. Run with env at runtime (example): **`docker run --rm -p 8080:8080 -e PORT=8080 --env-file .env guardian-angel`**
3. Pass the **same** variables as local dev (via **`--env-file .env`**, `-e`, or your cloud secret store). **Do not bake secrets into the image.**
4. The container listens on **`PORT`** (e.g. Cloud Run) or **`GUARDIAN_ANGEL_PORT`**, default **8000**.
5. For Firebase JSON keys, mount the file and set **`GOOGLE_APPLICATION_CREDENTIALS`** to the path **inside** the container.

---

## 8. Quick reference — environment variables

| Variable | Required? | Description |
|----------|-----------|-------------|
| `GUARDIAN_ANGEL_API_SECRET` | Yes | Shared secret for API authentication |
| `FIREBASE_PROJECT_ID` | Yes | Firebase / GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Usually yes (local) | Path to service account JSON |
| `GUARDIAN_ANGEL_HOST` | No | Bind host |
| `GUARDIAN_ANGEL_PORT` | No | Listen port (default 8000) |

---

## 9. Troubleshooting

| Symptom | Things to check |
|---------|------------------|
| **401** on POST | `Authorization` header matches `GUARDIAN_ANGEL_API_SECRET` exactly; no extra quotes in shell. |
| **Firebase / permission errors** | `GOOGLE_APPLICATION_CREDENTIALS` path is correct and readable; service account has Firestore access; `FIREBASE_PROJECT_ID` matches the project that owns the database. |
| **Address already in use** | Another process on port 8000; change `GUARDIAN_ANGEL_PORT`. |
| **Empty UI** | Data not written yet; send a test transmission; confirm Firestore rules allow the server’s writes. |
| **Dependency / lock errors** | Run **`uv sync`**. If `pyproject.toml` changed, run **`uv lock`** then **`uv sync`** and commit an updated **`uv.lock`**. |

---

## 10. Related documents

- **[`GUARDIAN_ANGEL_SPEC.md`](GUARDIAN_ANGEL_SPEC.md)** — full product and technical specification.
- **`README.md`** — project quickstart (to be added with the codebase).
