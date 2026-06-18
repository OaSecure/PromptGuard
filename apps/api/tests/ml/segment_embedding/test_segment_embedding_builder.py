import math

from app.atoms import TextRange
from app.ml.embedding import AtomEmbedding
from app.ml.segment_embedding import SegmentEmbeddingBuildRequest, SegmentEmbeddingPolicy, build_segment_embeddings
from app.segmenter import AnalysisSegment


def segment(segment_id: str, atom_ids: list[str], ordinal: int) -> AnalysisSegment:
    return AnalysisSegment(
        segment_id=segment_id,
        input_id="input-1",
        atom_ids=atom_ids,
        text="runtime text",
        original_range=TextRange(start=ordinal * 10, end=ordinal * 10 + 5),
        locations=[],
        segment_type="semantic",
        ordinal=ordinal,
    )


def embedding(atom_id: str, vector: list[float]) -> AtomEmbedding:
    return AtomEmbedding(atom_id=atom_id, vector=vector)


def request(
    segments: list[AnalysisSegment],
    atom_embeddings: list[AtomEmbedding],
    policy: SegmentEmbeddingPolicy | None = None,
) -> SegmentEmbeddingBuildRequest:
    return SegmentEmbeddingBuildRequest(
        input_id="input-1",
        segments=segments,
        atom_embeddings=atom_embeddings,
        embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
        policy=policy or SegmentEmbeddingPolicy(normalize_vectors=False),
    )


def test_segment_embedding_mean_pooling():
    result = build_segment_embeddings(
        request(
            [segment("s1", ["a1", "a2"], 0)],
            [embedding("a1", [1.0, 3.0]), embedding("a2", [3.0, 5.0])],
        )
    )

    assert result.failure is None
    assert len(result.segment_embeddings) == 1
    assert result.segment_embeddings[0].segment_id == "s1"
    assert result.segment_embeddings[0].vector == [2.0, 4.0]
    assert result.segment_embeddings[0].dimension == 2
    assert result.segment_embeddings[0].pooling == "mean"
    assert result.segment_embeddings[0].normalized is False


def test_segment_embedding_single_atom_boundary_preserves_vector():
    result = build_segment_embeddings(
        request(
            [segment("s1", ["a1"], 0)],
            [embedding("a1", [7.0, 11.0])],
        )
    )

    assert result.failure is None
    assert result.segment_embeddings[0].vector == [7.0, 11.0]
    assert result.segment_embeddings[0].dimension == 2


def test_segment_embedding_empty_request_returns_empty_result():
    result = build_segment_embeddings(request([], []))

    assert result.input_id == "input-1"
    assert result.segment_embeddings == []
    assert result.failure is None


def test_segment_embedding_weighted_mean_uses_uniform_weights_without_weight_field():
    result = build_segment_embeddings(
        request(
            [segment("s1", ["a1", "a2"], 0)],
            [embedding("a1", [2.0, 4.0]), embedding("a2", [6.0, 8.0])],
            SegmentEmbeddingPolicy(pooling="weighted_mean", normalize_vectors=False),
        )
    )

    assert result.failure is None
    assert result.segment_embeddings[0].vector == [4.0, 6.0]
    assert result.segment_embeddings[0].pooling == "weighted_mean"


def test_segment_embedding_normalizes_mean_vector():
    result = build_segment_embeddings(
        request(
            [segment("s1", ["a1", "a2"], 0)],
            [embedding("a1", [3.0, 0.0]), embedding("a2", [0.0, 3.0])],
            SegmentEmbeddingPolicy(normalize_vectors=True),
        )
    )

    vector = result.segment_embeddings[0].vector

    assert result.failure is None
    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)
    assert result.segment_embeddings[0].normalized is True


def test_segment_embedding_zero_vector_normalization_fails():
    result = build_segment_embeddings(
        request(
            [segment("s1", ["a1", "a2"], 0)],
            [embedding("a1", [1.0, 0.0]), embedding("a2", [-1.0, 0.0])],
            SegmentEmbeddingPolicy(normalize_vectors=True),
        )
    )

    assert result.segment_embeddings == []
    assert result.failure is not None
    assert result.failure.code == "SEGMENT_EMBEDDING_NORMALIZATION_FAILED"


def test_segment_embedding_preserves_segment_order():
    result = build_segment_embeddings(
        request(
            [segment("s2", ["a2"], 1), segment("s1", ["a1"], 0)],
            [embedding("a1", [1.0, 0.0]), embedding("a2", [0.0, 1.0])],
        )
    )

    assert result.failure is None
    assert [item.segment_id for item in result.segment_embeddings] == ["s2", "s1"]
    assert [item.vector for item in result.segment_embeddings] == [[0.0, 1.0], [1.0, 0.0]]


def test_segment_embedding_dimension_mismatch_fails():
    result = build_segment_embeddings(
        request(
            [segment("s1", ["a1", "a2"], 0)],
            [embedding("a1", [1.0, 0.0]), embedding("a2", [1.0, 0.0, 0.0])],
        )
    )

    assert result.segment_embeddings == []
    assert result.failure is not None
    assert result.failure.code == "SEGMENT_EMBEDDING_DIMENSION_MISMATCH"


def test_segment_embedding_missing_atom_embedding_fails_without_raw_text():
    result = build_segment_embeddings(
        request(
            [segment("s1", ["a1", "missing"], 0)],
            [embedding("a1", [1.0, 0.0])],
        )
    )

    assert result.segment_embeddings == []
    assert result.failure is not None
    assert result.failure.code == "SEGMENT_EMBEDDING_MISSING_ATOM"
    assert "runtime text" not in result.failure.message


def test_segment_embedding_empty_segment_atom_ids_fail():
    result = build_segment_embeddings(request([segment("s1", [], 0)], []))

    assert result.segment_embeddings == []
    assert result.failure is not None
    assert result.failure.code == "SEGMENT_EMBEDDING_EMPTY_SEGMENT"


def test_segment_embedding_invalid_vector_value_fails():
    result = build_segment_embeddings(request([segment("s1", ["a1"], 0)], [embedding("a1", [math.nan])]))

    assert result.segment_embeddings == []
    assert result.failure is not None
    assert result.failure.code == "SEGMENT_EMBEDDING_INVALID_VECTOR"
