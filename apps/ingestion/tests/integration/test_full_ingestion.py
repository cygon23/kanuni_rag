"""Integration tests: ingest all six fixtures through the real pipeline against Postgres.

Per PROJECT_SPEC.md §13, the metadata-extraction LLM call and the
embedding call are mocked (never real) even here — only the database
(and, where `tesseract` is installed, OCR) are real. See
`tests/integration/conftest.py` for the reachable-Postgres skip.
"""

import hashlib
from pathlib import Path
from typing import cast
from uuid import UUID

import asyncpg
from fakes import FakeEmbeddingProvider, FakeMetadataExtractionProvider, FakeOCREngine

from kanuni_ingest.embedding import EmbeddingProvider
from kanuni_ingest.metadata_extraction import MetadataExtractionProvider
from kanuni_ingest.models import ExtractedDocumentMetadata
from kanuni_ingest.pipeline import PipelineRunner
from kanuni_ingest.registry import DocumentRegistry
from kanuni_ingest.stages.ocr import OCREngine, TesseractOCREngine
from kanuni_ingest.storage import LocalFilesystemStorage

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


async def _seed_document(
    pool: asyncpg.Pool,
    *,
    pdf_bytes: bytes,
    storage: LocalFilesystemStorage,
    title: str,
    language: str = "en",
    reference_number: str | None = None,
) -> UUID:
    """Simulate the admin-upload fetch step: store the file and insert a `documents` row.

    Mirrors what `apps/api`'s upload endpoint does (ADR 0005: the two
    services share the database, not code), scoped down to exactly what
    these tests need to seed.
    """
    file_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    storage_path = f"{file_sha256}.pdf"
    await storage.write(storage_path, pdf_bytes)

    async with pool.acquire() as connection:
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
    return cast(UUID, document_id)


def _make_runner(
    tmp_path: Path,
    *,
    metadata_provider: MetadataExtractionProvider | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    ocr_engine: OCREngine | None = None,
) -> PipelineRunner:
    return PipelineRunner(
        storage=LocalFilesystemStorage(str(tmp_path)),
        ocr_engine=ocr_engine or FakeOCREngine(),
        ocr_languages="eng+swa",
        embedding_provider=embedding_provider or FakeEmbeddingProvider(),
        metadata_provider=metadata_provider or FakeMetadataExtractionProvider(),
        chunk_target_tokens=450,
        chunk_overlap_tokens=60,
    )


async def _fetch_document_row(pool: asyncpg.Pool, document_id: UUID) -> asyncpg.Record:
    async with pool.acquire() as connection:
        row = await connection.fetchrow("SELECT * FROM documents WHERE id = $1", document_id)
    assert row is not None
    return row


async def _count_chunks(pool: asyncpg.Pool, document_id: UUID) -> int:
    async with pool.acquire() as connection:
        count = await connection.fetchval(
            "SELECT count(*) FROM chunks WHERE document_id = $1", document_id
        )
    return int(count)


async def test_clean_native_text_document_is_fully_indexed(
    db_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """bot-2015-electronic-money.pdf: clean native text, no gazette number in the source."""
    pdf_bytes = (FIXTURES_DIR / "bot-2015-electronic-money.pdf").read_bytes()
    storage = LocalFilesystemStorage(str(tmp_path))
    document_id = await _seed_document(
        db_pool, pdf_bytes=pdf_bytes, storage=storage, title="Electronic Money Regulations"
    )
    runner = _make_runner(tmp_path)

    async with db_pool.acquire() as connection:
        await runner.run(connection, DocumentRegistry(connection), document_id)

    row = await _fetch_document_row(db_pool, document_id)
    assert row["pipeline_status"] == "indexed"
    assert row["status"] == "in_force"
    assert row["reference_number"] is None
    assert await _count_chunks(db_pool, document_id) > 0


async def test_swahili_document_is_fully_indexed(db_pool: asyncpg.Pool, tmp_path: Path) -> None:
    """bot-2019-huduma-ndogo-swahili.pdf: language=sw, real Swahili text is chunked."""
    pdf_bytes = (FIXTURES_DIR / "bot-2019-huduma-ndogo-swahili.pdf").read_bytes()
    storage = LocalFilesystemStorage(str(tmp_path))
    document_id = await _seed_document(
        db_pool,
        pdf_bytes=pdf_bytes,
        storage=storage,
        title="Kanuni za Matumizi ya Fedha za Kigeni",
        language="sw",
    )
    runner = _make_runner(tmp_path)

    async with db_pool.acquire() as connection:
        await runner.run(connection, DocumentRegistry(connection), document_id)

    row = await _fetch_document_row(db_pool, document_id)
    assert row["pipeline_status"] == "indexed"
    assert row["language"] == "sw"

    async with db_pool.acquire() as connection:
        chunk_contents = await connection.fetch(
            "SELECT content FROM chunks WHERE document_id = $1", document_id
        )
    assert any("Kanuni" in record["content"] for record in chunk_contents)


async def test_capital_adequacy_table_survives_chunking_as_markdown(
    db_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """bot-2023-capital-adequacy.pdf: the First Schedule table is stored as one Markdown chunk."""
    pdf_bytes = (FIXTURES_DIR / "bot-2023-capital-adequacy.pdf").read_bytes()
    storage = LocalFilesystemStorage(str(tmp_path))
    document_id = await _seed_document(
        db_pool,
        pdf_bytes=pdf_bytes,
        storage=storage,
        title="Capital Adequacy Regulations",
        reference_number="G.N. No. 727",
    )
    runner = _make_runner(tmp_path)

    async with db_pool.acquire() as connection:
        await runner.run(connection, DocumentRegistry(connection), document_id)

    row = await _fetch_document_row(db_pool, document_id)
    assert row["pipeline_status"] == "indexed"

    async with db_pool.acquire() as connection:
        chunk_contents = await connection.fetch(
            "SELECT content FROM chunks WHERE document_id = $1", document_id
        )
    assert any("Fully-fledged Banks" in record["content"] for record in chunk_contents)
    assert any("|---" in record["content"] for record in chunk_contents)


async def test_scanned_document_routes_through_ocr_and_still_indexes(
    db_pool: asyncpg.Pool, tmp_path: Path, require_tesseract: None
) -> None:
    """bot-2003-forex-listed-securities.pdf: no text layer — must route through real OCR."""
    pdf_bytes = (FIXTURES_DIR / "bot-2003-forex-listed-securities.pdf").read_bytes()
    storage = LocalFilesystemStorage(str(tmp_path))
    document_id = await _seed_document(
        db_pool,
        pdf_bytes=pdf_bytes,
        storage=storage,
        title="Foreign Exchange (Listed Securities) Regulations",
    )
    runner = _make_runner(tmp_path, ocr_engine=TesseractOCREngine())

    async with db_pool.acquire() as connection:
        await runner.run(connection, DocumentRegistry(connection), document_id)

    row = await _fetch_document_row(db_pool, document_id)
    assert row["pipeline_status"] == "indexed"
    assert await _count_chunks(db_pool, document_id) > 0


async def test_amendment_pair_produces_relation_and_status_updates(
    db_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """bot-2023-licensing-amendment.pdf amends bot-2014-licensing.pdf.

    Ingesting the original first and the amendment second must produce an
    `amends` `document_relations` row and promote the amendment's own
    status to `in_force`, without demoting the original (§7 stage 4).
    """
    storage = LocalFilesystemStorage(str(tmp_path))
    original_bytes = (FIXTURES_DIR / "bot-2014-licensing.pdf").read_bytes()
    amendment_bytes = (FIXTURES_DIR / "bot-2023-licensing-amendment.pdf").read_bytes()

    original_id = await _seed_document(
        db_pool,
        pdf_bytes=original_bytes,
        storage=storage,
        title="Licensing Regulations, 2014",
        reference_number="G.N. No. 297",
    )
    amendment_id = await _seed_document(
        db_pool,
        pdf_bytes=amendment_bytes,
        storage=storage,
        title="Licensing (Amendment) Regulations, 2022",
    )
    runner = _make_runner(tmp_path)

    async with db_pool.acquire() as connection:
        await runner.run(connection, DocumentRegistry(connection), original_id)
        await runner.run(connection, DocumentRegistry(connection), amendment_id)

    original_row = await _fetch_document_row(db_pool, original_id)
    amendment_row = await _fetch_document_row(db_pool, amendment_id)
    assert original_row["pipeline_status"] == "indexed"
    assert original_row["status"] == "in_force"
    assert amendment_row["pipeline_status"] == "indexed"
    assert amendment_row["status"] == "in_force"

    async with db_pool.acquire() as connection:
        relation = await connection.fetchrow(
            """
            SELECT * FROM document_relations
            WHERE from_document_id = $1 AND to_document_id = $2
            """,
            amendment_id,
            original_id,
        )
    assert relation is not None
    assert relation["relation"] == "amends"


async def test_resuming_after_a_mid_pipeline_failure_produces_no_duplicate_chunks(
    db_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """A crash after chunking but before indexing, then a rerun, must not duplicate chunks."""
    pdf_bytes = (FIXTURES_DIR / "bot-2014-licensing.pdf").read_bytes()
    storage = LocalFilesystemStorage(str(tmp_path))
    document_id = await _seed_document(
        db_pool, pdf_bytes=pdf_bytes, storage=storage, title="Licensing Regulations, 2014"
    )

    class _FailingEmbeddingProvider:
        async def embed_batch(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("simulated crash mid-pipeline")

    failing_runner = _make_runner(tmp_path, embedding_provider=_FailingEmbeddingProvider())

    async with db_pool.acquire() as connection:
        await failing_runner.run(connection, DocumentRegistry(connection), document_id)

    failed_row = await _fetch_document_row(db_pool, document_id)
    assert failed_row["pipeline_status"] == "failed"
    assert await _count_chunks(db_pool, document_id) == 0

    working_runner = _make_runner(tmp_path)
    async with db_pool.acquire() as connection:
        await working_runner.run(connection, DocumentRegistry(connection), document_id)

    indexed_row = await _fetch_document_row(db_pool, document_id)
    assert indexed_row["pipeline_status"] == "indexed"
    first_run_chunk_count = await _count_chunks(db_pool, document_id)
    assert first_run_chunk_count > 0

    async with db_pool.acquire() as connection:
        await working_runner.run(connection, DocumentRegistry(connection), document_id)

    # Already indexed: PipelineRunner.run short-circuits, so re-running again
    # (as an operator retry might) must not change the chunk count either.
    assert await _count_chunks(db_pool, document_id) == first_run_chunk_count


async def test_metadata_extraction_never_calls_a_real_provider(
    db_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """The metadata-extraction call must go through the provider interface, per §13."""
    pdf_bytes = (FIXTURES_DIR / "bot-2014-licensing.pdf").read_bytes()
    storage = LocalFilesystemStorage(str(tmp_path))
    document_id = await _seed_document(
        db_pool, pdf_bytes=pdf_bytes, storage=storage, title="Licensing Regulations, 2014"
    )
    fake_provider = FakeMetadataExtractionProvider(ExtractedDocumentMetadata())
    runner = _make_runner(tmp_path, metadata_provider=fake_provider)

    async with db_pool.acquire() as connection:
        await runner.run(connection, DocumentRegistry(connection), document_id)

    assert fake_provider.calls, "expected the fake provider's extract() to have been called"
