"""Fetches source documents from sources.yaml or admin upload; dedupes by SHA-256.

The admin-upload half of this stage runs synchronously inside apps/api's
upload endpoint (it has its own copy of the hash/store logic — the two
services share the database, not code; see ADR 0005). This module covers
the other half: downloading a document from a configured source URL.
"""

import hashlib

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from kanuni_ingest.storage import DocumentStorage

_MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_SECONDS = 30.0


@retry(
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential_jitter(initial=1, max=10),
    reraise=True,
)
async def fetch_from_url(url: str) -> bytes:
    """Download a document from a source URL.

    Args:
        url: The document URL, as configured in `sources.yaml`.

    Returns:
        The downloaded document bytes.
    """
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def compute_sha256(content: bytes) -> str:
    """Compute the SHA-256 hex digest of document content, used for dedup.

    Args:
        content: The raw document bytes.

    Returns:
        The lowercase hex digest.
    """
    return hashlib.sha256(content).hexdigest()


async def store_document(storage: DocumentStorage, content: bytes) -> tuple[str, str]:
    """Compute a document's hash and persist it under a hash-derived path.

    Args:
        storage: The storage backend to write to.
        content: The raw document bytes.

    Returns:
        A tuple of `(file_sha256, storage_path)`.
    """
    file_sha256 = compute_sha256(content)
    storage_path = f"{file_sha256}.pdf"
    await storage.write(storage_path, content)
    return file_sha256, storage_path
