from collections.abc import Callable
from typing import Protocol


class AtomEmbeddingBackend(Protocol):
    model_version: str
    dimension: int
    is_frozen: bool

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        ...


class AtomEmbeddingModelLoader:
    def __init__(self, backend_factory: Callable[[str], AtomEmbeddingBackend]) -> None:
        self._backend_factory = backend_factory
        self._cache: dict[str, AtomEmbeddingBackend] = {}

    def get_model(self, model_name: str) -> AtomEmbeddingBackend:
        if model_name not in self._cache:
            self._cache[model_name] = self._backend_factory(model_name)
        return self._cache[model_name]
