"""Supersession and amendment relationship detection and management between documents.

Implements PROJECT_SPEC.md §7 stage 4: extract metadata via regex first
(reference number, issue date, cited-document relations — all directly
verifiable against source text), then a single LLM call to supplement
fields regex can't reliably determine (issuing body, effective date) and
to catch anything regex missed. Regex results take precedence where both
exist, since they're deterministic and directly traceable to the source
text; the LLM only fills gaps.
"""

from uuid import UUID

import structlog

from kanuni_ingest import regex_extraction
from kanuni_ingest.metadata_extraction import MetadataExtractionProvider
from kanuni_ingest.models import (
    DocumentStatus,
    ExtractedDocumentMetadata,
    RelatedDocumentReference,
)
from kanuni_ingest.registry import DocumentRegistryProtocol

logger = structlog.get_logger()


def _related_documents_from_regex(
    relation: str | None, citations: list[str]
) -> list[RelatedDocumentReference]:
    """Build related-document references from a regex relation keyword and citations.

    Args:
        relation: The relation keyword regex detected for the document as a
            whole (`"supersedes"`, `"amends"`, `"refers_to"`, or `None`).
        citations: Reference numbers regex found cited in the text.

    Returns:
        One reference per citation, all sharing the detected relation, or
        an empty list if no relation keyword was found.
    """
    if relation is None:
        return []
    return [
        RelatedDocumentReference(reference_number=reference_number, relation=relation)  # type: ignore[arg-type]
        for reference_number in citations
    ]


def _dedupe_related_documents(
    items: list[RelatedDocumentReference],
) -> list[RelatedDocumentReference]:
    """Deduplicate related-document references by (reference_number, relation).

    Args:
        items: Related-document references from any number of sources, in
            priority order — earlier entries win on a duplicate key.

    Returns:
        The deduplicated list, preserving first-seen order.
    """
    merged: dict[tuple[str, str], RelatedDocumentReference] = {}
    for item in items:
        merged.setdefault((item.reference_number, item.relation), item)
    return list(merged.values())


def extract_metadata_candidates(text: str) -> ExtractedDocumentMetadata:
    """Extract whatever metadata regex alone can determine from a document's text.

    Args:
        text: The document's full extracted text.

    Returns:
        Metadata with `reference_number` and `related_documents` populated
        where regex found them; `issuing_body` and `effective_date` are
        always `None` here — regex doesn't attempt those.
    """
    reference_number = regex_extraction.extract_reference_number(text)
    issued_date = regex_extraction.extract_issued_date(text)
    relation = regex_extraction.classify_relation_keyword(text)
    citations = regex_extraction.find_cited_reference_numbers(text)
    return ExtractedDocumentMetadata(
        reference_number=reference_number,
        issued_date=issued_date,
        related_documents=_related_documents_from_regex(relation, citations),
    )


async def apply_metadata_and_versioning(
    document_id: UUID,
    text: str,
    *,
    registry: DocumentRegistryProtocol,
    metadata_provider: MetadataExtractionProvider,
) -> ExtractedDocumentMetadata:
    """Extract metadata, detect supersession/amendment relations, and apply both.

    A document that supersedes another flips the superseded document's
    status to `superseded`; an amendment or a bare reference does not — the
    referenced document remains in force. The document being processed is
    itself promoted from `unknown` to `in_force` once its metadata has been
    successfully extracted and validated — for a pure amendment, this (not
    a change to the amended document's status) is the "status update" the
    ingestion of an amendment produces.

    Args:
        document_id: The document being processed.
        text: The document's full extracted text.
        registry: Registry used to resolve cited documents and apply updates.
        metadata_provider: Provider used for the supplementary LLM extraction call.

    Returns:
        The merged, validated extracted metadata.

    Raises:
        MetadataValidationError: Propagated from the provider on validation
            failure — the caller treats this as a stage failure per §7's
            failure policy.
    """
    regex_metadata = extract_metadata_candidates(text)
    llm_metadata = await metadata_provider.extract(text)

    metadata = ExtractedDocumentMetadata(
        reference_number=regex_metadata.reference_number or llm_metadata.reference_number,
        issuing_body=llm_metadata.issuing_body,
        issued_date=regex_metadata.issued_date or llm_metadata.issued_date,
        effective_date=llm_metadata.effective_date,
        related_documents=_dedupe_related_documents(
            regex_metadata.related_documents + llm_metadata.related_documents
        ),
    )

    await registry.fill_missing_metadata(
        document_id,
        reference_number=metadata.reference_number,
        issuing_body=metadata.issuing_body,
        issued_date=metadata.issued_date,
        effective_date=metadata.effective_date,
    )

    for related in metadata.related_documents:
        target = await registry.find_by_reference_number(related.reference_number)
        if target is None:
            logger.warning(
                "related_document_not_found",
                document_id=str(document_id),
                reference_number=related.reference_number,
                relation=related.relation,
            )
            continue

        await registry.create_relation(
            from_document_id=document_id,
            to_document_id=target.id,
            relation=related.relation,
        )

        if related.relation == "supersedes":
            await registry.update_status(target.id, DocumentStatus.SUPERSEDED)

    await registry.update_status(document_id, DocumentStatus.IN_FORCE)

    return metadata
