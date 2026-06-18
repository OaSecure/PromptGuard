import math
import time
from collections.abc import Callable

from app.atoms.models import AnalysisAtom, PipelineFailure
from app.ml.embedding.loader import AtomEmbeddingBackend, AtomEmbeddingModelLoader
from app.ml.embedding.models import AtomEmbedding, AtomEmbeddingRequest, AtomEmbeddingResult

DEFAULT_MICRO_BATCH_SIZE = 16

EMBEDDING_MODEL_UNAVAILABLE = "EMBEDDING_MODEL_UNAVAILABLE"
EMBEDDING_TIMEOUT = "EMBEDDING_TIMEOUT"
EMBEDDING_INVALID_OUTPUT = "EMBEDDING_INVALID_OUTPUT"
EMBEDDING_MODEL_NOT_FROZEN = "EMBEDDING_MODEL_NOT_FROZEN"


def embed_atoms(
    request: AtomEmbeddingRequest,
    loader: AtomEmbeddingModelLoader | None = None,
) -> AtomEmbeddingResult:
    if not request.atoms:
        return _result(request, embeddings=[], dimension=0)

    if loader is None:
        return _failure_result(request, EMBEDDING_MODEL_UNAVAILABLE)

    started_at = time.monotonic()
    if _timed_out(started_at, request.timeout_ms):
        return _failure_result(request, EMBEDDING_TIMEOUT)

    try:
        backend = loader.get_model(request.model_name)
    except Exception:
        return _failure_result(request, EMBEDDING_MODEL_UNAVAILABLE)

    if getattr(backend, "is_frozen", True) is not True:
        return _failure_result(request, EMBEDDING_MODEL_NOT_FROZEN)

    embeddings: list[AtomEmbedding] = []
    expected_dimension: int | None = None

    for batch in _micro_batches(request.atoms, DEFAULT_MICRO_BATCH_SIZE):
        if _timed_out(started_at, request.timeout_ms):
            return _failure_result(request, EMBEDDING_TIMEOUT)
        try:
            vectors = backend.embed_texts([atom.text for atom in batch], request.normalize_vectors)
        except Exception:
            return _failure_result(request, EMBEDDING_INVALID_OUTPUT)

        batch_dimension = _validated_dimension(vectors, len(batch), backend)
        if batch_dimension is None:
            return _failure_result(request, EMBEDDING_INVALID_OUTPUT)
        if expected_dimension is None:
            expected_dimension = batch_dimension
        elif expected_dimension != batch_dimension:
            return _failure_result(request, EMBEDDING_INVALID_OUTPUT)

        embeddings.extend(
            AtomEmbedding(atom_id=atom.atom_id, vector=[float(value) for value in vector])
            for atom, vector in zip(batch, vectors)
        )

        if _timed_out(started_at, request.timeout_ms):
            return _failure_result(request, EMBEDDING_TIMEOUT)

    return _result(request, embeddings=embeddings, dimension=expected_dimension or 0, backend=backend)


def _micro_batches(atoms: list[AnalysisAtom], batch_size: int) -> list[list[AnalysisAtom]]:
    return [atoms[index : index + batch_size] for index in range(0, len(atoms), batch_size)]


def _validated_dimension(
    vectors: list[list[float]],
    expected_count: int,
    backend: AtomEmbeddingBackend,
) -> int | None:
    if len(vectors) != expected_count or not vectors:
        return None

    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        return None

    dimension = dimensions.pop()
    if dimension <= 0:
        return None
    if getattr(backend, "dimension", dimension) != dimension:
        return None

    for vector in vectors:
        if any(not isinstance(value, int | float) or not math.isfinite(value) for value in vector):
            return None
    return dimension


def _timed_out(started_at: float, timeout_ms: int, now: Callable[[], float] = time.monotonic) -> bool:
    return timeout_ms <= 0 or ((now() - started_at) * 1000) > timeout_ms


def _result(
    request: AtomEmbeddingRequest,
    *,
    embeddings: list[AtomEmbedding],
    dimension: int,
    backend: AtomEmbeddingBackend | None = None,
) -> AtomEmbeddingResult:
    return AtomEmbeddingResult(
        input_id=request.input_id,
        embeddings=embeddings,
        embedding_model_version=request.model_name if backend is None else backend.model_version,
        dimension=dimension,
        normalized=request.normalize_vectors,
        failure=None,
    )


def _failure_result(request: AtomEmbeddingRequest, code: str) -> AtomEmbeddingResult:
    return AtomEmbeddingResult(
        input_id=request.input_id,
        embeddings=[],
        embedding_model_version=request.model_name,
        dimension=0,
        normalized=request.normalize_vectors,
        failure=_failure(code),
    )


def _failure(code: str) -> PipelineFailure:
    return PipelineFailure(code=code, message=code, metadata={"failure_code": code})
