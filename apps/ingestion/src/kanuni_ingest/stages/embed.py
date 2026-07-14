"""Embed stage: batch-embeds chunk content and attaches the resulting vectors."""

from kanuni_ingest.embedding import EmbeddingProvider
from kanuni_ingest.models import DocumentChunk


async def embed_chunks(
    chunks: list[DocumentChunk], *, embedding_provider: EmbeddingProvider
) -> list[DocumentChunk]:
    """Embed every chunk's content and return chunks with `embedding` populated.

    Args:
        chunks: Chunks produced by the chunking stage.
        embedding_provider: Provider used to compute embeddings.

    Returns:
        The same chunks, each with its `embedding` field set.
    """
    if not chunks:
        return []
    vectors = await embedding_provider.embed_batch([chunk.content for chunk in chunks])
    return [
        chunk.model_copy(update={"embedding": vector})
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
