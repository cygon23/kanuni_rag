"""Document registry: source lookups and document metadata records, backed by Postgres."""

from datetime import date
from typing import Literal, Protocol
from uuid import UUID

import asyncpg

from kanuni_ingest.db import document_relations_repository, documents_repository
from kanuni_ingest.models import DocumentRecord, DocumentStatus, PipelineStage


class DocumentRegistryProtocol(Protocol):
    """The registry operations the pipeline and versioning depend on.

    A `Protocol` (rather than requiring the concrete, Postgres-backed
    `DocumentRegistry`) so unit tests can pass an in-memory fake without
    a real database — see `tests/fakes.py`.
    """

    async def find_pending_documents(self) -> list[DocumentRecord]: ...

    async def find_by_id(self, document_id: UUID) -> DocumentRecord | None: ...

    async def find_by_reference_number(self, reference_number: str) -> DocumentRecord | None: ...

    async def update_pipeline_status(self, document_id: UUID, stage: PipelineStage) -> None: ...

    async def update_status(self, document_id: UUID, status: DocumentStatus) -> None: ...

    async def fill_missing_metadata(
        self,
        document_id: UUID,
        *,
        reference_number: str | None,
        issuing_body: str | None,
        issued_date: date | None,
        effective_date: date | None,
    ) -> None: ...

    async def create_relation(
        self,
        *,
        from_document_id: UUID,
        to_document_id: UUID,
        relation: Literal["supersedes", "amends", "refers_to"],
    ) -> None: ...


class DocumentRegistry:
    """Looks up and updates document records on behalf of the pipeline and worker."""

    def __init__(self, connection: asyncpg.Connection) -> None:
        """Wrap a database connection with registry operations.

        Args:
            connection: An open database connection, held for the duration
                of processing one document.
        """
        self._connection = connection

    async def find_pending_documents(self) -> list[DocumentRecord]:
        """List every document whose pipeline has not finished or permanently failed.

        Returns:
            Documents the worker should (re)process, oldest first.
        """
        return await documents_repository.find_pending(self._connection)

    async def find_by_id(self, document_id: UUID) -> DocumentRecord | None:
        """Fetch a document by id.

        Args:
            document_id: The document's id.

        Returns:
            The document, or `None` if it doesn't exist.
        """
        return await documents_repository.find_by_id(self._connection, document_id)

    async def find_by_reference_number(self, reference_number: str) -> DocumentRecord | None:
        """Fetch a document by its reference number, for versioning resolution.

        Args:
            reference_number: The normalized reference number to look up.

        Returns:
            The document, or `None` if no ingested document has that
            reference number.
        """
        return await documents_repository.find_by_reference_number(
            self._connection, reference_number
        )

    async def update_pipeline_status(self, document_id: UUID, stage: PipelineStage) -> None:
        """Advance (or fail) a document's pipeline status.

        Args:
            document_id: The document to update.
            stage: The new pipeline status.
        """
        await documents_repository.update_pipeline_status(self._connection, document_id, stage)

    async def update_status(self, document_id: UUID, status: DocumentStatus) -> None:
        """Update a document's in-force/superseded/repealed status.

        Args:
            document_id: The document to update.
            status: The new status.
        """
        await documents_repository.update_status(self._connection, document_id, status)

    async def fill_missing_metadata(
        self,
        document_id: UUID,
        *,
        reference_number: str | None,
        issuing_body: str | None,
        issued_date: date | None,
        effective_date: date | None,
    ) -> None:
        """Fill any currently-unset metadata fields from extraction results.

        Args:
            document_id: The document to update.
            reference_number: Extracted reference number, if any.
            issuing_body: Extracted issuing body, if any.
            issued_date: Extracted issue date, if any.
            effective_date: Extracted effective date, if any.
        """
        await documents_repository.fill_missing_metadata(
            self._connection,
            document_id,
            reference_number=reference_number,
            issuing_body=issuing_body,
            issued_date=issued_date,
            effective_date=effective_date,
        )

    async def create_relation(
        self,
        *,
        from_document_id: UUID,
        to_document_id: UUID,
        relation: Literal["supersedes", "amends", "refers_to"],
    ) -> None:
        """Record a relation between two documents.

        Args:
            from_document_id: The document that supersedes/amends/refers to another.
            to_document_id: The document being superseded/amended/referred to.
            relation: The relation type.
        """
        await document_relations_repository.create_relation(
            self._connection,
            from_document_id=from_document_id,
            to_document_id=to_document_id,
            relation=relation,
        )
