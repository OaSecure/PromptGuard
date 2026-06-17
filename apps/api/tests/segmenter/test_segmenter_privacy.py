from app.atoms import AnalysisAtom, TextRange
from app.segmenter import AtomEmbedding, SegmentBuildRequest, SegmentPolicy, build_segments
from app.segmenter.metadata import project_segment_metadata, project_segment_result_metadata


def atom(text: str) -> AnalysisAtom:
    return AnalysisAtom(
        atom_id="a1",
        input_id="input-1",
        block_id="block-1",
        text=text,
        original_range=TextRange(start=0, end=len(text)),
        location={"kind": "page", "page": 1},
        atom_type="paragraph",
        ordinal=0,
    )


def test_segment_text_not_persisted():
    raw_text = "SECRET-SEGMENT-TEXT"
    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=[atom(raw_text)],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[1.0, 0.0])],
            segment_policy=SegmentPolicy(),
        )
    )

    payload = project_segment_result_metadata(result)

    assert raw_text not in str(payload)
    assert "text" not in str(payload)


def test_segmenter_does_not_emit_action_fields():
    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=[atom("safe")],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[1.0, 0.0])],
            segment_policy=SegmentPolicy(),
        )
    )

    payload = result.model_dump()
    forbidden = {"action", "recommended_action", "reason_code", "user_notice", "label_scores"}
    assert forbidden.isdisjoint(payload["segments"][0])


def test_segmenter_does_not_emit_reason_code():
    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=[atom("safe")],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[1.0, 0.0])],
            segment_policy=SegmentPolicy(),
        )
    )

    assert "reason_code" not in str(result.model_dump())


def test_segment_metadata_projection_uses_safe_allowlist():
    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=[atom("safe")],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[1.0, 0.0])],
            segment_policy=SegmentPolicy(),
        )
    )

    payload = project_segment_metadata(result.segments[0], result.segmenter_version)

    assert set(payload) == {"segment_id", "atom_count", "segment_type", "length_bucket", "location_kind", "segmenter_version"}
