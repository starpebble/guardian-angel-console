"""Application settings from environment (see GUARDIAN_ANGEL_SPEC.md §8)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (parent of ``guardian_angel/``) — stable even if cwd is elsewhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_DOTENV_PATH) if _DOTENV_PATH.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    guardian_angel_api_secret: str | None = Field(
        default=None,
        description="Shared secret for POST /api/v1/transmissions (Bearer or X-Guardian-Angel-Token)",
    )
    # Spec §7 alternate env name:
    guardian_angel_shared_secret: str | None = Field(default=None)

    firebase_project_id: str | None = Field(default=None)

    google_application_credentials: str | None = Field(
        default=None,
        description="Path to GCP service account JSON (same as GOOGLE_APPLICATION_CREDENTIALS)",
    )

    triage_system_label: str = Field(default="SALT")

    medic_notes_collection: str = Field(
        default="Medic Notes",
        description="Firestore collection id for AI-transcribed medic notes (spaces allowed; match your console)",
        validation_alias=AliasChoices(
            "GUARDIAN_ANGEL_MEDIC_NOTES_COLLECTION",
            "medic_notes_collection",
        ),
    )

    git_sha: str | None = Field(default=None, validation_alias="GIT_SHA")

    def effective_api_secret(self) -> str | None:
        return self.guardian_angel_api_secret or self.guardian_angel_shared_secret


@lru_cache
def get_settings() -> Settings:
    # Populate ``os.environ`` so Firebase ADC and other libs see the same values as Pydantic.
    if _DOTENV_PATH.is_file():
        load_dotenv(_DOTENV_PATH, override=False)
    return Settings()
