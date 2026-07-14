"""Single source of application configuration, read from environment variables."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
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
    storage_local_path: str = "./data/documents"
    max_upload_size_bytes: int = 100 * 1024 * 1024

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
