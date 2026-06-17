from app.atoms import AnalysisAtom, TextRange
from app.segmenter import AtomEmbedding, SegmentBuildRequest, SegmentPolicy, build_segments


def atom(atom_id: str, text: str, ordinal: int, block_id: str = "block-1", start: int = 0) -> AnalysisAtom:
    return AnalysisAtom(
        atom_id=atom_id,
        input_id="input-1",
        block_id=block_id,
        text=text,
        original_range=TextRange(start=start, end=start + len(text)),
        location={"kind": "page", "page": ordinal},
        atom_type="paragraph",
        ordinal=ordinal,
    )


def embedding(atom_id: str, vector: list[float]) -> AtomEmbedding:
    return AtomEmbedding(atom_id=atom_id, vector=vector)


def test_segmenter_structure_fallback():
    atoms = [atom("a1", "alpha", 0, "block-1"), atom("a2", "beta", 1, "block-2")]

    result = build_segments(
        SegmentBuildRequest(input_id="input-1", atoms=atoms, atom_embeddings=[], segment_policy=SegmentPolicy())
    )

    assert result.boundary_scores == []
    assert [segment.segment_type for segment in result.segments] == ["single_atom", "single_atom"]


def test_missing_embedding_triggers_structure_fallback():
    atoms = [atom("a1", "alpha", 0), atom("a2", "beta", 1)]

    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=atoms,
            atom_embeddings=[embedding("a1", [1.0, 0.0])],
            segment_policy=SegmentPolicy(),
        )
    )

    assert result.boundary_scores == []
    assert all(segment.segment_type != "semantic" for segment in result.segments)


def test_dimension_mismatch_triggers_fallback_or_failure():
    atoms = [atom("a1", "alpha", 0), atom("a2", "beta", 1)]

    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=atoms,
            atom_embeddings=[embedding("a1", [1.0, 0.0]), embedding("a2", [1.0])],
            segment_policy=SegmentPolicy(),
        )
    )

    assert result.failure is not None
    assert result.failure.code == "invalid_embedding_vector"
    assert all(segment.segment_type != "semantic" for segment in result.segments)


def test_huge_segment_is_split_by_max_chars():
    atoms = [
        atom(f"a{i}", "x" * 10, i, "block-1", start=i * 10)
        for i in range(6)
    ]
    embeddings = [embedding(f"a{i}", [1.0, 0.0]) for i in range(6)]

    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=atoms,
            atom_embeddings=embeddings,
            segment_policy=SegmentPolicy(target_chars=100, max_chars=25),
        )
    )

    assert all(len(segment.text) <= 25 for segment in result.segments)
    assert any(segment.segment_type == "size_fallback" for segment in result.segments)


def test_segment_policy_not_extended_for_percentile_threshold():
    fields = set(SegmentPolicy.model_fields)

    assert "percentile_threshold" not in fields
    assert "cosine_percentile" not in fields
