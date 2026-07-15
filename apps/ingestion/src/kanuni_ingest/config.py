"""Single source of ingestion-worker configuration, read from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Kanuni ingestion worker and CLI.

    All fields are backed by an environment variable prefixed with
    ``KANUNI_`` (e.g. ``KANUNI_WORKER_POLL_INTERVAL_SECONDS``). This class
    is the only place the ingestion service reads environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="KANUNI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://kanuni:kanuni@localhost:5432/kanuni"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    metadata_llm_provider: str = "groq"
    metadata_llm_model: str = "llama-3.1-8b-instant"
    groq_api_key: str = ""
    worker_poll_interval_seconds: float = 5.0
    ocr_languages: str = "eng+swa"
    chunk_target_tokens: int = 450
    chunk_overlap_tokens: int = 60
    admin_api_base_url: str = "http://localhost:8000"
    admin_api_key: str = ""

    # Observability (§11, Phase 6) — bare env vars (no KANUNI_ prefix),
    # shared verbatim with apps/api's identically-named settings fields.
    sentry_dsn: str = Field(default="", validation_alias="SENTRY_DSN")
    release_sha: str = Field(default="dev", validation_alias="RELEASE_SHA")

    # Storage (§4.4) — Supabase Storage, via SupabaseStorage in storage.py.
    # Bare env vars, shared verbatim with apps/api's identically-named fields.
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    storage_bucket: str = "documents"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance.

    Returns:
        The ingestion service settings, constructed once per process from
        the environment and cached for subsequent calls.
    """
    return Settings()
