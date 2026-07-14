"""Parameterized SQL for the `document_relations` table."""

from typing import Literal
from uuid import UUID

import asyncpg


async def create_relation(
    connection: asyncpg.Connection,
    *,
    from_document_id: UUID,
    to_document_id: UUID,
    relation: Literal["supersedes", "amends", "refers_to"],
) -> None:
    """Record a relation between two documents, per PROJECT_SPEC.md §6.

    Idempotent: re-running versioning for the same document pair and
    relation is a no-op rather than a duplicate row or a constraint error,
    which matters for resumability (§4.2).

    Args:
        connection: An open database connection.
        from_document_id: The document that supersedes/amends/refers to another.
        to_document_id: The document being superseded/amended/referred to.
        relation: The relation type.
    """
    await connection.execute(
        """
        INSERT INTO document_relations (from_document_id, to_document_id, relation)
        VALUES ($1, $2, $3)
        ON CONFLICT (from_document_id, to_document_id, relation) DO NOTHING
        """,
        from_document_id,
        to_document_id,
        relation,
    )
