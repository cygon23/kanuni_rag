"""Seeds and fully ingests the 6 Phase 1 fixtures for evals.yml's CI run.

Mirrors `apps/ingestion/tests/integration/test_full_ingestion.py`'s seeding
pattern (ADR 0005: ingestion and api share a database, not code) rather
than going through the admin-upload HTTP API + a separately-running
worker, since a one-shot CI job has no long-lived worker process to poll.

Uses the REAL `Bgem3EmbeddingProvider` and, for the one scanned fixture,
real `TesseractOCREngine` — both are required for the retrieval eval's
dense-search results to mean anything. Metadata extraction stays on a
trivial no-op stand-in: `versioning.py` determines `reference_number` and
`amends`/`supersedes` relations via regex on the source text (see its
module docstring), never from the LLM metadata call, so a real Groq call
here would add cost and a new failure mode without changing eval-relevant
output. Titles and reference numbers are instead seeded directly, matching
the values `evals/golden/qa.jsonl`'s questions assume.
"""

import asyncio
import hashlib
import os
from pathlib import Path
from uuid import UUID

import asyncpg

from kanuni_ingest.embedding import Bgem3EmbeddingProvider
from kanuni_ingest.models import ExtractedDocumentMetadata
from kanuni_ingest.pipeline import PipelineRunner
from kanuni_ingest.registry import DocumentRegistry
from kanuni_ingest.stages.ocr import TesseractOCREngine
from kanuni_ingest.storage import LocalFilesystemStorage

FIXTURES_DIR = Path(__file__).parent.parent / "apps" / "ingestion" / "tests" / "fixtures"
STORAGE_PATH = Path(__file__).parent.parent / "data" / "eval_documents"

# (filename, title, language, reference_number) — reference_number is only
# seeded where it's cleanly known ahead of ingestion; None lets regex
# extraction (see module docstring) fill it in from the source text.
_FIXTURES: list[tuple[str, str, str, str | None]] = [
    ("bot-2015-electronic-money.pdf", "Electronic Money Regulations", "en", None),
    (
        "bot-2019-huduma-ndogo-swahili.pdf",
        "Kanuni za Matumizi ya Fedha za Kigeni",
        "sw",
        None,
    ),
    ("bot-2023-capital-adequacy.pdf", "Capital Adequacy Regulations", "en", "G.N. No. 727"),
    (
        "bot-2003-forex-listed-securities.pdf",
        "Foreign Exchange (Listed Securities) Regulations",
        "en",
        None,
    ),
    ("bot-2014-licensing.pdf", "Licensing Regulations, 2014", "en", "G.N. No. 297"),
    ("bot-2023-licensing-amendment.pdf", "Licensing (Amendment) Regulations, 2022", "en", None),
]


class _NoOpMetadataExtractionProvider:
    """Satisfies `MetadataExtractionProvider` without an LLM call — see module docstring."""

    async def extract(self, text: str) -> ExtractedDocumentMetadata:
        return ExtractedDocumentMetadata()


async def _seed_document(
    pool: asyncpg.Pool,
    *,
    pdf_bytes: bytes,
    storage: LocalFilesystemStorage,
    title: str,
    language: str,
    reference_number: str | None,
) -> UUID:
    file_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    storage_path = f"{file_sha256}.pdf"
    await storage.write(storage_path, pdf_bytes)

    async with pool.acquire() as connection:
        existing = await connection.fetchval(
            "SELECT id FROM documents WHERE file_sha256 = $1", file_sha256
        )
        if existing is not None:
            return UUID(str(existing))

        document_id = await connection.fetchval(
            """
            INSERT INTO documents (
                source_id, title, doc_type, jurisdiction, issuing_body,
                reference_number, language, status, file_sha256, storage_path,
                pipeline_status
            )
            VALUES ('bot', $1, 'regulation', 'Tanzania', 'Bank of Tanzania',
                    $2, $3, 'unknown', $4, $5, 'fetched')
            RETURNING id
            """,
            title,
            reference_number,
            language,
            file_sha256,
            storage_path,
        )
    return UUID(str(document_id))


async def main() -> None:
    """Seed and fully ingest all 6 fixtures, real embeddings/OCR, idempotently."""
    database_url = os.environ.get(
        "KANUNI_DATABASE_URL", "postgresql://kanuni:kanuni@localhost:5432/kanuni"
    )
    STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    storage = LocalFilesystemStorage(str(STORAGE_PATH))

    runner = PipelineRunner(
        storage=storage,
        ocr_engine=TesseractOCREngine(),
        ocr_languages="eng+swa",
        embedding_provider=Bgem3EmbeddingProvider("BAAI/bge-m3"),
        metadata_provider=_NoOpMetadataExtractionProvider(),
        chunk_target_tokens=450,
        chunk_overlap_tokens=60,
    )

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    if pool is None:
        raise RuntimeError("failed to connect to the database")

    # Sequential, and licensing before its amendment, so the amendment's
    # `amends` relation resolves against an already-registered original
    # (see PipelineRunner.run / versioning.py).
    for filename, title, language, reference_number in _FIXTURES:
        print(f"Ingesting {filename}...")
        pdf_bytes = (FIXTURES_DIR / filename).read_bytes()
        document_id = await _seed_document(
            pool,
            pdf_bytes=pdf_bytes,
            storage=storage,
            title=title,
            language=language,
            reference_number=reference_number,
        )
        async with pool.acquire() as connection:
            status = await connection.fetchval(
                "SELECT pipeline_status FROM documents WHERE id = $1", document_id
            )
            if status == "indexed":
                print(f"  already indexed, skipping ({document_id})")
                continue
            await runner.run(connection, DocumentRegistry(connection), document_id)
        print(f"  indexed ({document_id})")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
