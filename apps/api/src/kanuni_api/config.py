"""Single source of application configuration, read from environment variables."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "staging", "production"]
LogLevel = Literal["debug", "info", "warning", "error"]


class Settings(BaseSettings):
    """Runtime configuration for the Kanuni API, sourced from the environment.

    All fields are backed by an environment variable prefixed with
    ``KANUNI_`` (e.g. ``KANUNI_LOG_LEVEL``). Values are loaded from the
    process environment and, for local development, from a ``.env`` file at
    the repository root. Secrets must never be hardcoded; this class is the
    only place environment variables are read.
    """

    model_config = SettingsConfigDict(
        env_prefix="KANUNI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = "development"
    log_level: LogLevel = "info"
    api_port: int = 8000
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    database_url: str = "postgresql://kanuni:kanuni@localhost:5432/kanuni"
    max_upload_size_bytes: int = 100 * 1024 * 1024

    # Storage (§4.4) — Supabase Storage, via SupabaseStorage in storage.py.
    # supabase_url/supabase_service_role_key are bare env vars (no
    # KANUNI_ prefix), shared verbatim with apps/ingestion's identically-
    # named settings — one Supabase project, same convention as
    # sentry_dsn/release_sha below.
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    storage_bucket: str = "documents"

    # Retrieval (§8.1) — every threshold lives here, not in code, per spec.
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    dense_top_k: int = 30
    sparse_top_k: int = 30
    rrf_k: int = 60
    fusion_top_k: int = 20
    rerank_top_k: int = 6

    # Generation (§8.3) — Groq, provider-abstracted (never hardcoded in
    # business logic). groq_api_key reads the bare GROQ_API_KEY (no
    # KANUNI_ prefix), the provider's own conventional variable name, kept
    # distinct from kanuni_ingest's KANUNI_GROQ_API_KEY (its own metadata-
    # extraction call — see .env.example's Phase 1 section).
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_fallback_provider: str = ""
    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    confidence_refuse_threshold: float = 0.30
    confidence_caution_threshold: float = 0.55
    active_prompt_version: str = "v1"

    # Evaluation only (§10, §13) — the judge model that scores faithfulness
    # for evals/run_answer_eval.py. Deliberately a different, smaller Groq
    # model than llm_model: judging your own answers with the same model
    # that produced them is a well-known source of inflated eval scores.
    eval_judge_llm_model: str = "llama-3.1-8b-instant"

    # Observability (§11, Phase 6). sentry_dsn reads the bare SENTRY_DSN
    # (no KANUNI_ prefix — one GlitchTip/Sentry-protocol project's DSN,
    # shared verbatim across api/ingestion/web; see .env.example). Empty
    # string disables the SDK (its own documented no-op behavior) rather
    # than needing an if-configured branch here. release_sha would
    # ideally be set per-deploy to the deployed commit SHA, but
    # deploy.yml's Hugging Face Spaces target has no scripted way to set
    # a Space secret per-deploy (unlike Fly's old `--env` flag) — see
    # docs/NEEDS.md's Hugging Face Spaces section. "dev" locally (and,
    # for now, on every deploy) is a deliberately obvious marker.
    sentry_dsn: str = Field(default="", validation_alias="SENTRY_DSN")
    release_sha: str = Field(default="dev", validation_alias="RELEASE_SHA")

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_comma_separated_origins(cls, value: object) -> object:
        """Allow ``cors_allowed_origins`` to be supplied as a comma-separated string.

        ``NoDecode`` disables pydantic-settings' default JSON decoding for
        this field, since a plain comma-separated string (not a JSON array)
        is the ergonomic way to set a list in an env file.
        """
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance.

    Returns:
        The application settings, constructed once per process from the
        environment and cached for subsequent calls.
    """
    return Settings()
