"""Loads `sources.yaml`: the single source of truth for issuing body and jurisdiction.

`documents.source_id` is a free-text slug, not a foreign key (ADR 0002) —
its validity against the configured sources, and the issuing body and
jurisdiction it implies, are resolved here, once, at upload time.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from kanuni_api.exceptions import ValidationFailedError

_DEFAULT_SOURCES_PATH = Path("sources.yaml")


class SourceConfig(BaseModel):
    """One `sources.yaml` source entry's top-level (non-document) fields."""

    name: str
    issuing_body: str
    jurisdiction: str


@lru_cache
def load_sources(sources_path: Path = _DEFAULT_SOURCES_PATH) -> dict[str, SourceConfig]:
    """Load and cache every configured source.

    Args:
        sources_path: Path to the `sources.yaml` file.

    Returns:
        A mapping of source id to its configuration.
    """
    raw = yaml.safe_load(sources_path.read_text())
    return {
        source_id: SourceConfig(
            name=entry["name"],
            issuing_body=entry["issuing_body"],
            jurisdiction=entry["jurisdiction"],
        )
        for source_id, entry in raw.get("sources", {}).items()
    }


def resolve_source(source_id: str) -> SourceConfig:
    """Resolve a source id to its configuration, validating it is known.

    Args:
        source_id: The slug supplied by the uploader.

    Returns:
        The source's configuration.

    Raises:
        ValidationFailedError: If `source_id` matches no entry in `sources.yaml`.
    """
    sources = load_sources()
    source = sources.get(source_id)
    if source is None:
        raise ValidationFailedError(f"Unknown source_id: {source_id!r}")
    return source
