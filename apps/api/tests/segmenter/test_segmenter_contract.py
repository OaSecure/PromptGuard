from app.atoms import AnalysisAtom, TextRange
from app.segmenter import (
    AtomEmbedding,
    SegmentBuildRequest,
    SegmentPolicy,
    build_segments,
)


def atom(atom_id: str, text: str, ordinal: int, block_id: str = "block-1", start: int = 0) -> AnalysisAtom:
    return AnalysisAtom(
        atom_id=atom_id,
        input_id="input-1",
        block_id=block_id,
        text=text,
        original_range=TextRange(start=start, end=start + len(text)),
        location=None,
        atom_type="paragraph",
        ordinal=ordinal,
    )


def embedding(atom_id: str, vector: list[float]) -> AtomEmbedding:
    return AtomEmbedding(atom_id=atom_id, vector=vector)


def test_no_atoms_returns_empty_segments():
    result = build_segments(SegmentBuildRequest(input_id="input-1", atoms=[], atom_embeddings=[], segment_policy=SegmentPolicy()))

    assert result.segments == []
    assert result.boundary_scores == []
    assert result.failure is None


def test_adjacent_similarity_creates_boundary():
    atoms = [atom("a1", "contract terms", 0), atom("a2", "payment clause", 1, start=14), atom("a3", "login token", 2, start=29)]
    embeddings = [embedding("a1", [1.0, 0.0]), embedding("a2", [0.95, 0.05]), embedding("a3", [0.0, 1.0])]

    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=atoms,
            atom_embeddings=embeddings,
            segment_policy=SegmentPolicy(cosine_break_threshold=0.72, target_chars=100, max_chars=200),
        )
    )

    assert [score.boundary_selected for score in result.boundary_scores] == [False, True]
    assert [segment.segment_type for segment in result.segments] == ["semantic", "single_atom"]


def test_segment_contains_atom_membership():
    atoms = [atom("a1", "alpha", 0), atom("a2", " beta", 1, start=5)]
    embeddings = [embedding("a1", [1.0, 0.0]), embedding("a2", [1.0, 0.0])]

    result = build_segments(
        SegmentBuildRequest(input_id="input-1", atoms=atoms, atom_embeddings=embeddings, segment_policy=SegmentPolicy())
    )

    assert result.segments[0].atom_ids == ["a1", "a2"]
    assert result.segments[0].text == "alpha beta"


def test_boundary_scores_are_emitted_for_adjacent_atoms():
    atoms = [atom("a1", "one", 0), atom("a2", "two", 1, start=3), atom("a3", "three", 2, start=6)]
    embeddings = [embedding("a1", [1.0, 0.0]), embedding("a2", [0.8, 0.2]), embedding("a3", [0.0, 1.0])]

    result = build_segments(
        SegmentBuildRequest(input_id="input-1", atoms=atoms, atom_embeddings=embeddings, segment_policy=SegmentPolicy())
    )

    assert [(score.left_atom_id, score.right_atom_id) for score in result.boundary_scores] == [("a1", "a2"), ("a2", "a3")]


def test_segment_output_order_is_deterministic():
    atoms = [atom("a1", "alpha", 0), atom("a2", "omega", 1, start=5)]
    embeddings = [embedding("a1", [1.0, 0.0]), embedding("a2", [0.0, 1.0])]
    request = SegmentBuildRequest(input_id="input-1", atoms=atoms, atom_embeddings=embeddings, segment_policy=SegmentPolicy())

    first = build_segments(request)
    second = build_segments(request)

    assert [segment.segment_id for segment in first.segments] == [segment.segment_id for segment in second.segments]
    assert [segment.atom_ids for segment in first.segments] == [segment.atom_ids for segment in second.segments]


def test_segmenter_uses_singular_failure_field():
    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=[atom("a1", "bad vector", 0)],
            atom_embeddings=[embedding("a1", [float("nan")])],
            segment_policy=SegmentPolicy(),
        )
    )

    payload = result.model_dump()
    assert "failure" in payload
    assert "failures" not in payload
    assert result.failure is not None
