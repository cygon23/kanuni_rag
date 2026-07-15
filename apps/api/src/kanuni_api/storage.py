"""Storage interface for original source documents, swappable per PROJECT_SPEC.md §4.4.

Mirrors `kanuni_ingest.storage` — the two services share the database, not
code (ADR 0005), so each keeps its own small copy of this interface.

Backed by Supabase Storage's plain REST API via httpx (no `supabase-py`
dependency — matches this codebase's existing pattern of talking to
external HTTP APIs directly, e.g. `GroqLLMProvider`). The bucket is
public: Kanuni's corpus is public Bank of Tanzania regulatory text, so
serving it back out doesn't need an authenticated read path — only
writes (uploads) need the service-role key, which never reaches the
browser (see `apps/web/src/lib/serverConfig.ts` for the analogous
API-key pattern on the frontend side).
"""

from typing import Protocol

import httpx


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


def public_url(*, base_url: str, bucket: str, storage_path: str) -> str:
    """Build a Supabase Storage public object URL.

    Args:
        base_url: The Supabase project URL, e.g. `https://<ref>.supabase.co`.
        bucket: The storage bucket name.
        storage_path: The object's path within the bucket.

    Returns:
        A stable, unauthenticated URL serving the object directly — the
        bucket is public, so this needs no signing or auth header. Used
        directly (not via a `DocumentStorage` instance) since it's pure
        string formatting, no I/O — see
        `services/query_service.py`'s citation-resolution code.
    """
    return f"{base_url.rstrip('/')}/storage/v1/object/public/{bucket}/{storage_path}"


class SupabaseStorage:
    """Uploads documents to a Supabase Storage bucket via its REST API."""

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
