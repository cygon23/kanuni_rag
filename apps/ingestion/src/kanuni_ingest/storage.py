"""Storage interface for original source documents, swappable per PROJECT_SPEC.md §4.4.

`SupabaseStorage` backs the real worker (`__main__.py`) and
`stages/fetch.py`'s URL-sourced documents; `LocalFilesystemStorage`
backs tests only now (§13: no test may call a real external API, and
Supabase Storage is one) — kept deliberately, not a leftover, since it's
a fast, real, dependency-free stand-in for
`apps/ingestion/tests/integration/test_full_ingestion.py`'s real-pipeline
tests, which need a working storage backend but must never touch the
network. Every caller depends only on the :class:`DocumentStorage`
protocol.
"""

from pathlib import Path
from typing import Protocol

import httpx


class DocumentStorage(Protocol):
    """Persists and retrieves the original bytes of an uploaded or fetched document."""

    async def write(self, storage_path: str, content: bytes) -> None:
        """Persist document bytes at the given storage path.

        Args:
            storage_path: A storage-backend-relative path identifying the
                document (e.g. its SHA-256 hex digest with a `.pdf` suffix).
            content: The raw document bytes.
        """
        ...

    async def read(self, storage_path: str) -> bytes:
        """Retrieve previously stored document bytes.

        Args:
            storage_path: The storage path returned by a prior `write` call.

        Returns:
            The raw document bytes.
        """
        ...


def public_url(*, base_url: str, bucket: str, storage_path: str) -> str:
    """Build a Supabase Storage public object URL.

    Args:
        base_url: The Supabase project URL, e.g. `https://<ref>.supabase.co`.
        bucket: The storage bucket name.
        storage_path: The object's path within the bucket.

    Returns:
        A stable, unauthenticated URL — the bucket is public (Kanuni's
        corpus is public regulatory text), used here for `read()` too,
        so only writes need the service-role key.
    """
    return f"{base_url.rstrip('/')}/storage/v1/object/public/{bucket}/{storage_path}"


class SupabaseStorage:
    """Persists and retrieves documents in a Supabase Storage bucket via its REST API.

    Mirrors `apps/api/src/kanuni_api/storage.py`'s copy (ADR 0005: own
    copy, not shared code) — this one additionally implements `read()`,
    since `PipelineRunner` reads the original bytes back out for
    extraction/OCR, which `apps/api` no longer needs to do.
    """

    def __init__(self, *, base_url: str, service_role_key: str, bucket: str) -> None:
        """Configure the storage backend.

        Args:
            base_url: The Supabase project URL.
            service_role_key: Service-role secret — bypasses bucket
                policies/RLS, so this must never reach the browser.
            bucket: The storage bucket name.
        """
        self._base_url = base_url.rstrip("/")
        self._service_role_key = service_role_key
        self._bucket = bucket

    async def write(self, storage_path: str, content: bytes) -> None:
        """Upload document bytes to the bucket, overwriting any existing object.

        Args:
            storage_path: A storage-relative path, e.g. `"<sha256>.pdf"`.
            content: The raw document bytes.

        Raises:
            httpx.HTTPStatusError: If the upload fails.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/storage/v1/object/{self._bucket}/{storage_path}",
                headers={
                    "Authorization": f"Bearer {self._service_role_key}",
                    "apikey": self._service_role_key,
                    "Content-Type": "application/pdf",
                    "x-upsert": "true",
                },
                content=content,
            )
            response.raise_for_status()

    async def read(self, storage_path: str) -> bytes:
        """Download document bytes from the bucket's public URL.

        Args:
            storage_path: The storage-relative path previously written.

        Returns:
            The raw document bytes.

        Raises:
            httpx.HTTPStatusError: If the object doesn't exist or the
                download otherwise fails.
        """
        url = public_url(base_url=self._base_url, bucket=self._bucket, storage_path=storage_path)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content


class LocalFilesystemStorage:
    """Stores documents as files under a local base directory.

    Test-only now (see this module's docstring) — production code uses
    `SupabaseStorage`.
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

    async def read(self, storage_path: str) -> bytes:
        """Read document bytes from a file under the base directory.

        Args:
            storage_path: The storage-relative path previously written.

        Returns:
            The raw document bytes.
        """
        return (self._base_path / storage_path).read_bytes()
