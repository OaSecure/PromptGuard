import math

from app.atoms.models import PipelineFailure
from app.ml.embedding.models import AtomEmbedding
from app.ml.segment_embedding.models import (
    SegmentEmbedding,
    SegmentEmbeddingBuildRequest,
    SegmentEmbeddingBuildResult,
    SegmentEmbeddingPolicy,
)
from app.segmenter.models import AnalysisSegment

SEGMENT_EMBEDDING_MISSING_ATOM = "SEGMENT_EMBEDDING_MISSING_ATOM"
SEGMENT_EMBEDDING_DIMENSION_MISMATCH = "SEGMENT_EMBEDDING_DIMENSION_MISMATCH"
SEGMENT_EMBEDDING_EMPTY_SEGMENT = "SEGMENT_EMBEDDING_EMPTY_SEGMENT"
SEGMENT_EMBEDDING_INVALID_VECTOR = "SEGMENT_EMBEDDING_INVALID_VECTOR"
SEGMENT_EMBEDDING_NORMALIZATION_FAILED = "SEGMENT_EMBEDDING_NORMALIZATION_FAILED"


def build_segment_embeddings(request: SegmentEmbeddingBuildRequest) -> SegmentEmbeddingBuildResult:
    embeddings_by_atom_id = {embedding.atom_id: embedding for embedding in request.atom_embeddings}
    segment_embeddings: list[SegmentEmbedding] = []
    expected_dimension: int | None = None

    for segment in request.segments:
        vectors_or_failure = _vectors_for_segment(segment, embeddings_by_atom_id)
        if isinstance(vectors_or_failure, PipelineFailure):
            return _failure_result(request, vectors_or_failure)

        vectors = vectors_or_failure
        dimension = len(vectors[0])
        if expected_dimension is None:
            expected_dimension = dimension
        elif expected_dimension != dimension:
            return _failure_result(request, _failure(SEGMENT_EMBEDDING_DIMENSION_MISMATCH))

        pooled = _pool_vectors(vectors, request.policy)
        if pooled is None:
            return _failure_result(request, _failure(SEGMENT_EMBEDDING_NORMALIZATION_FAILED))

        segment_embeddings.append(
            SegmentEmbedding(
                segment_id=segment.segment_id,
                vector=pooled,
                embedding_model_version=request.embedding_model_version,
                dimension=len(pooled),
                pooling=request.policy.pooling,
                normalized=request.policy.normalize_vectors,
            )
        )

    return SegmentEmbeddingBuildResult(
        input_id=request.input_id,
        segment_embeddings=segment_embeddings,
        failure=None,
    )


def _vectors_for_segment(
    segment: AnalysisSegment,
    embeddings_by_atom_id: dict[str, AtomEmbedding],
) -> list[list[float]] | PipelineFailure:
    if not segment.atom_ids:
        return _failure(SEGMENT_EMBEDDING_EMPTY_SEGMENT)

    vectors: list[list[float]] = []
    dimension: int | None = None
    for atom_id in segment.atom_ids:
        embedding = embeddings_by_atom_id.get(atom_id)
        if embedding is None:
            return _failure(SEGMENT_EMBEDDING_MISSING_ATOM)
        if not embedding.vector or any(not isinstance(value, int | float) or not math.isfinite(value) for value in embedding.vector):
            return _failure(SEGMENT_EMBEDDING_INVALID_VECTOR)
        if dimension is None:
            dimension = len(embedding.vector)
        elif dimension != len(embedding.vector):
            return _failure(SEGMENT_EMBEDDING_DIMENSION_MISMATCH)
        vectors.append([float(value) for value in embedding.vector])
    return vectors


def _pool_vectors(vectors: list[list[float]], policy: SegmentEmbeddingPolicy) -> list[float] | None:
    pooled = _pool_by_policy(vectors, policy)
    if policy.normalize_vectors:
        return _normalize(pooled)
    return pooled


def _pool_by_policy(vectors: list[list[float]], policy: SegmentEmbeddingPolicy) -> list[float]:
    if policy.pooling == "weighted_mean":
        return _uniform_weighted_mean(vectors)
    return _mean(vectors)


def _mean(vectors: list[list[float]]) -> list[float]:
    count = len(vectors)
    return [sum(vector[index] for vector in vectors) / count for index in range(len(vectors[0]))]


def _uniform_weighted_mean(vectors: list[list[float]]) -> list[float]:
    return _mean(vectors)


def _normalize(vector: list[float]) -> list[float] | None:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0 or not math.isfinite(norm):
        return None
    return [value / norm for value in vector]


def _failure_result(
    request: SegmentEmbeddingBuildRequest,
    failure: PipelineFailure,
) -> SegmentEmbeddingBuildResult:
    return SegmentEmbeddingBuildResult(
        input_id=request.input_id,
        segment_embeddings=[],
        failure=failure,
    )


def _failure(code: str) -> PipelineFailure:
    return PipelineFailure(code=code, message=code, metadata={"failure_code": code})
