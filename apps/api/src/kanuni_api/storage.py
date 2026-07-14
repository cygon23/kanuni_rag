"""Storage interface for original source documents, swappable per PROJECT_SPEC.md §4.4.

Mirrors `kanuni_ingest.storage` — the two services share the database, not
code (ADR 0005), so each keeps its own small copy of this interface.
"""

from pathlib import Path
from typing import Protocol


class DocumentStorage(Protocol):
    """Persists the original bytes of an uploaded document."""

    async def write(self, storage_path: str, content: bytes) -> None:
        """Persist document bytes at the given storage path.

        Args:
            storage_path: A storage-backend-relative path identifying the
                document (e.g. its SHA-256 hex digest with a `.pdf` suffix).
            content: The raw document bytes.
        """
        ...


class LocalFilesystemStorage:
    """Stores documents as files under a local base directory.

    Used for local development and tests; a Supabase Storage (or other
    S3-compatible) implementation is expected to replace this in a deployed
    environment.
    """

    def __init__(self, base_path: str) -> None:
        """Initialize the storage backend, creating the base directory if needed.

        Args:
            base_path: Directory under which document files are stored.
        """
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    async def write(self, storage_path: str, content: bytes) -> None:
        """Write document bytes to a file under the base directory.

        Args:
            storage_path: A storage-relative path, e.g. `"<sha256>.pdf"`.
            content: The raw document bytes.
        """
        destination = self._base_path / storage_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
