import math

from app.atoms import AnalysisAtom, TextRange
from app.ml.embedding import (
    AtomEmbeddingModelLoader,
    AtomEmbeddingRequest,
    QWEN3_EMBEDDING_MODEL,
    embed_atoms,
)


class FakeBackend:
    model_version = QWEN3_EMBEDDING_MODEL
    dimension = 2
    is_frozen = True

    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self.calls: list[tuple[list[str], bool]] = []
        self.vectors = vectors

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        self.calls.append((texts, normalize))
        if self.vectors is not None:
            return self.vectors[: len(texts)]
        return [[float(index + 1), 0.0] for index, _ in enumerate(texts)]


class RaisingBackend(FakeBackend):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self.exc = exc

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        raise self.exc


def atom(atom_id: str, text: str, ordinal: int) -> AnalysisAtom:
    return AnalysisAtom(
        atom_id=atom_id,
        input_id="input-1",
        block_id="block-1",
        text=text,
        original_range=TextRange(start=ordinal * 10, end=ordinal * 10 + len(text)),
        location=None,
        atom_type="paragraph",
        ordinal=ordinal,
    )


def request(atoms: list[AnalysisAtom], timeout_ms: int = 1_000) -> AtomEmbeddingRequest:
    return AtomEmbeddingRequest(
        input_id="input-1",
        atoms=atoms,
        model_name=QWEN3_EMBEDDING_MODEL,
        normalize_vectors=True,
        timeout_ms=timeout_ms,
    )


def loader_for(backend: FakeBackend) -> AtomEmbeddingModelLoader:
    return AtomEmbeddingModelLoader(lambda model_name: backend)


def test_qwen_model_loaded_once():
    calls: list[str] = []

    def factory(model_name: str) -> FakeBackend:
        calls.append(model_name)
        return FakeBackend()

    loader = AtomEmbeddingModelLoader(factory)

    assert loader.get_model(QWEN3_EMBEDDING_MODEL) is loader.get_model(QWEN3_EMBEDDING_MODEL)
    assert calls == [QWEN3_EMBEDDING_MODEL]


def test_atom_embedding_order_preserved():
    atoms = [atom("a1", "first", 0), atom("a2", "second", 1), atom("a3", "third", 2)]
    backend = FakeBackend(vectors=[[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])

    result = embed_atoms(request(atoms), loader_for(backend))

    assert result.failure is None
    assert [embedding.atom_id for embedding in result.embeddings] == ["a1", "a2", "a3"]
    assert [embedding.vector for embedding in result.embeddings] == [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]


def test_empty_atoms_returns_empty_embeddings():
    result = embed_atoms(request([]), loader=None)

    assert result.input_id == "input-1"
    assert result.embeddings == []
    assert result.embedding_model_version == QWEN3_EMBEDDING_MODEL
    assert result.dimension == 0
    assert result.normalized is True
    assert result.failure is None


def test_empty_atoms_does_not_load_model():
    calls: list[str] = []
    loader = AtomEmbeddingModelLoader(lambda model_name: calls.append(model_name) or FakeBackend())

    result = embed_atoms(request([]), loader)

    assert result.failure is None
    assert calls == []


def test_non_empty_atoms_without_loader_returns_model_unavailable():
    result = embed_atoms(request([atom("a1", "secret text", 0)]), loader=None)

    assert result.embeddings == []
    assert result.failure is not None
    assert result.failure.code == "EMBEDDING_MODEL_UNAVAILABLE"
    assert "secret text" not in result.failure.message


def test_embedding_worker_timeout_returns_failure():
    result = embed_atoms(request([atom("a1", "slow", 0)], timeout_ms=0), loader_for(FakeBackend()))

    assert result.embeddings == []
    assert result.failure is not None
    assert result.failure.code == "EMBEDDING_TIMEOUT"


def test_embedding_invalid_vector_count_returns_failure():
    backend = FakeBackend(vectors=[[1.0, 0.0]])
    atoms = [atom("a1", "first", 0), atom("a2", "second", 1)]

    result = embed_atoms(request(atoms), loader_for(backend))

    assert result.embeddings == []
    assert result.failure is not None
    assert result.failure.code == "EMBEDDING_INVALID_OUTPUT"


def test_embedding_dimension_mismatch_returns_failure():
    backend = FakeBackend(vectors=[[1.0, 0.0], [1.0, 0.0, 0.0]])
    atoms = [atom("a1", "first", 0), atom("a2", "second", 1)]

    result = embed_atoms(request(atoms), loader_for(backend))

    assert result.embeddings == []
    assert result.failure is not None
    assert result.failure.code == "EMBEDDING_INVALID_OUTPUT"


def test_embedding_invalid_vector_value_returns_failure():
    backend = FakeBackend(vectors=[[math.nan, 0.0]])

    result = embed_atoms(request([atom("a1", "first", 0)]), loader_for(backend))

    assert result.embeddings == []
    assert result.failure is not None
    assert result.failure.code == "EMBEDDING_INVALID_OUTPUT"


def test_qwen_model_frozen():
    backend = FakeBackend()
    loader = loader_for(backend)

    assert loader.get_model(QWEN3_EMBEDDING_MODEL).is_frozen is True


def test_embedding_model_not_frozen_returns_failure():
    backend = FakeBackend()
    backend.is_frozen = False

    result = embed_atoms(request([atom("a1", "first", 0)]), loader_for(backend))

    assert result.embeddings == []
    assert result.failure is not None
    assert result.failure.code == "EMBEDDING_MODEL_NOT_FROZEN"


def test_atom_embedding_result_uses_singular_failure_field():
    result = embed_atoms(request([atom("a1", "first", 0)]), loader=None)
    payload = result.model_dump()

    assert "failure" in payload
    assert "failures" not in payload
