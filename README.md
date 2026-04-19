# Guardian Angel

Web console for incident command and medic triage workflows. 

## Spec

For spec driven development, please see [`GUARDIAN_ANGEL_SPEC.md`](GUARDIAN_ANGEL_SPEC.md) and [`developer.md`](developer.md).  Built with Cursor and OpenAI Codex.

## Repos

Guardian Angel Components:

1. https://github.com/starpebble/guardian-angel-console
2. https://github.com/starpebble/guardian-angel-radio-app
3. https://github.com/starpebble/guardian-angel-workflow

## Quick start

Dependencies are managed with **[uv](https://docs.astral.sh/uv/)** (`pyproject.toml` + `uv.lock`).

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed, then from the repository root:

```bash
uv sync
uv run uvicorn guardian_angel.main:app --reload --host 127.0.0.1 --port 8000
```

`uv sync` creates `.venv/` (if missing), installs locked dependencies, and installs this package in editable mode. You can also activate `.venv` and run `uvicorn` directly.

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Docker (cloud / production)

```bash
docker build -t guardian-angel .
docker run --rm -p 8080:8080 -e PORT=8080 --env-file .env guardian-angel
```

Cloud Run and many platforms set **`PORT`**; the image listens on **`PORT`** or **`GUARDIAN_ANGEL_PORT`**, default **8000**. Do not bake secrets into the image — inject **`GUARDIAN_ANGEL_API_SECRET`**, Firebase settings, and credential paths at runtime (see [`developer.md`](developer.md)).

