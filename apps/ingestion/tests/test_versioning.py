"""Tests for versioning: supersession/amendment detection and status updates."""

from uuid import uuid4

import pytest
from fakes import FakeDocumentRegistry, FakeMetadataExtractionProvider, make_document_record

from kanuni_ingest.exceptions import MetadataValidationError
from kanuni_ingest.models import DocumentStatus, ExtractedDocumentMetadata, RelatedDocumentReference
from kanuni_ingest.versioning import apply_metadata_and_versioning, extract_metadata_candidates


def test_extract_metadata_candidates_finds_reference_and_relation() -> None:
    """Regex candidates should carry through reference_number and detected relations."""
    text = (
        "Banking and Financial Institutions (Licensing) (Amendment)\n"
        "GOVERNMENT NOTICE NO 13 published on 20/01/2023\n"
        "1. These Regulations amend GN. No. 297 of 2014 by deleting regulation 40."
    )

    metadata = extract_metadata_candidates(text)

    assert metadata.reference_number == "G.N. No. 13"
    assert metadata.related_documents == [
        RelatedDocumentReference(reference_number="G.N. No. 297", relation="amends")
    ]


@pytest.mark.asyncio
async def test_amendment_creates_amends_relation_without_changing_amended_status() -> None:
    """An amendment records an 'amends' relation and leaves the amended document in_force."""
    amended = make_document_record(reference_number="G.N. No. 297", status=DocumentStatus.IN_FORCE)
    amending_id = uuid4()
    amending = make_document_record(document_id=amending_id, status=DocumentStatus.UNKNOWN)
    registry = FakeDocumentRegistry([amended, amending])
    provider = FakeMetadataExtractionProvider()

    await apply_metadata_and_versioning(
        amending_id,
        "1. These Regulations amend GN. No. 297 of 2014 by deleting regulation 40.",
        registry=registry,
        metadata_provider=provider,
    )

    assert (amending_id, amended.id, "amends") in registry.relations_created
    assert (amended.id, DocumentStatus.SUPERSEDED) not in registry.status_updates
    assert (amending_id, DocumentStatus.IN_FORCE) in registry.status_updates


@pytest.mark.asyncio
async def test_supersession_flips_superseded_document_status() -> None:
    """A document that supersedes another must flip the other's status to superseded."""
    old_document = make_document_record(
        reference_number="G.N. No. 9", status=DocumentStatus.IN_FORCE
    )
    new_document_id = uuid4()
    new_document = make_document_record(document_id=new_document_id)
    registry = FakeDocumentRegistry([old_document, new_document])
    provider = FakeMetadataExtractionProvider()

    await apply_metadata_and_versioning(
        new_document_id,
        "This circular supersedes GN. No. 9 of 2022 in its entirety.",
        registry=registry,
        metadata_provider=provider,
    )

    assert (new_document_id, old_document.id, "supersedes") in registry.relations_created
    assert (old_document.id, DocumentStatus.SUPERSEDED) in registry.status_updates
    assert (new_document_id, DocumentStatus.IN_FORCE) in registry.status_updates


@pytest.mark.asyncio
async def test_related_document_not_yet_ingested_is_skipped_not_fatal() -> None:
    """A citation to a document that hasn't been ingested yet must not fail the pipeline."""
    document_id = uuid4()
    registry = FakeDocumentRegistry([make_document_record(document_id=document_id)])
    provider = FakeMetadataExtractionProvider()

    metadata = await apply_metadata_and_versioning(
        document_id,
        "This circular supersedes GN. No. 999 of 1999, which was never ingested.",
        registry=registry,
        metadata_provider=provider,
    )

    assert metadata.related_documents
    assert registry.relations_created == []
    assert (document_id, DocumentStatus.IN_FORCE) in registry.status_updates


@pytest.mark.asyncio
async def test_llm_metadata_fills_gaps_regex_cannot_determine() -> None:
    """issuing_body and effective_date, which regex never attempts, should come from the LLM."""
    document_id = uuid4()
    registry = FakeDocumentRegistry([make_document_record(document_id=document_id)])
    provider = FakeMetadataExtractionProvider(
        ExtractedDocumentMetadata(issuing_body="Bank of Tanzania")
    )

    metadata = await apply_metadata_and_versioning(
        document_id,
        "A regulation with no gazette number in its text at all.",
        registry=registry,
        metadata_provider=provider,
    )

    assert metadata.issuing_body == "Bank of Tanzania"
    assert metadata.reference_number is None


@pytest.mark.asyncio
async def test_metadata_validation_failure_propagates() -> None:
    """A provider validation failure must propagate — the caller treats it as a stage failure."""
    document_id = uuid4()
    registry = FakeDocumentRegistry([make_document_record(document_id=document_id)])
    provider = FakeMetadataExtractionProvider()
    provider.raise_validation_error = True

    with pytest.raises(MetadataValidationError):
        await apply_metadata_and_versioning(
            document_id, "irrelevant text", registry=registry, metadata_provider=provider
        )
