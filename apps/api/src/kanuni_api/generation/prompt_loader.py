"""Loads the active versioned prompt file and fills in the tagged context block (§8.3)."""

from pathlib import Path
from uuid import UUID

from kanuni_api.models.document import DocumentSummary
from kanuni_api.models.retrieval import ScoredChunk

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt_template(version: str) -> str:
    """Load a versioned prompt file's raw template.

    Args:
        version: The prompt version, e.g. `"v1"`.

    Returns:
        The prompt template text, with `{context_block}` still unfilled.
    """
    return (_PROMPTS_DIR / f"answer_{version}.md").read_text()


def build_system_prompt(
    version: str,
    chunks: list[ScoredChunk],
    documents_by_id: dict[UUID, DocumentSummary],
) -> str:
    """Fill the versioned prompt template's context block with tagged chunks.

    Each chunk is tagged `[chunk:<id>] (<doc title>, <reference_number>,
    <section_ref>, status)` per §8.3, so the model can cite it and — for
    non-`in_force` documents — is prompted to disclose that status.

    Args:
        version: The prompt version to load.
        chunks: The reranked chunks to present as context, in order.
        documents_by_id: Document metadata for every chunk's `document_id`.

    Returns:
        The complete system prompt, ready to send to the LLM provider.
    """
    context_lines = []
    for chunk in chunks:
        document = documents_by_id[chunk.document_id]
        tag = (
            f"[chunk:{chunk.chunk_id}] ({document.title}, "
            f"{document.reference_number or 'no reference number'}, "
            f"{chunk.section_ref or 'no section reference'}, {document.status.value})"
        )
        context_lines.append(f"{tag}\n{chunk.content}")

    context_block = "\n\n".join(context_lines)
    template = load_prompt_template(version)
    return template.replace("{context_block}", context_block)
