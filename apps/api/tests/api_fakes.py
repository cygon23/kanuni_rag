"""Test doubles for the API's provider interfaces (§13: never call the real thing)."""

from collections.abc import AsyncIterator

from kanuni_api.generation.llm_client import GenerationChunk


class FakeEmbeddingProvider:
    """Returns a deterministic fixed-size vector instead of running bge-m3."""

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions
        self.calls: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return [float(len(text) % 7)] * self.dimensions


class FakeRerankerProvider:
    """Returns configurable (or length-based default) scores instead of running the reranker."""

    def __init__(self, scores: list[float] | None = None) -> None:
        self._scores = scores
        self.calls: list[tuple[str, list[str]]] = []

    async def score(self, question: str, candidates: list[str]) -> list[float]:
        self.calls.append((question, candidates))
        if self._scores is not None:
            return self._scores
        return [float(len(candidate)) for candidate in candidates]


class FakeDocumentStorage:
    """Stores document bytes in memory instead of calling Supabase Storage."""

    def __init__(self) -> None:
        self.writes: dict[str, bytes] = {}

    async def write(self, storage_path: str, content: bytes) -> None:
        self.writes[storage_path] = content


class FakeLLMProvider:
    """Yields a scripted sequence of text deltas, then a usage chunk, instead of calling Groq."""

    def __init__(
        self,
        text_deltas: list[str] | None = None,
        *,
        prompt_tokens: int = 100,
        completion_tokens: int = 50,
        raise_error: Exception | None = None,
    ) -> None:
        self._text_deltas = text_deltas if text_deltas is not None else ["An answer."]
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._raise_error = raise_error
        self.calls: list[tuple[str, str]] = []

    async def generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[GenerationChunk]:
        self.calls.append((system_prompt, user_prompt))
        if self._raise_error is not None:
            raise self._raise_error
        for delta in self._text_deltas:
            yield GenerationChunk(text_delta=delta)
        yield GenerationChunk(
            prompt_tokens=self._prompt_tokens, completion_tokens=self._completion_tokens
        )
