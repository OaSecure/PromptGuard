from app.atoms import AnalysisAtom, TextRange
from app.mapping import (
    LexicalSignal,
    SignalMappingPolicy,
    SignalMappingRequest,
    map_signals_to_segments,
    project_signal_mapping_metadata,
)
from app.segmenter import AnalysisSegment


def test_mapped_signals_do_not_include_raw_matched_value_or_segment_text():
    result = map_signals_to_segments(
        SignalMappingRequest(
            input_id="input-1",
            segments=[
                AnalysisSegment(
                    segment_id="seg-1",
                    input_id="input-1",
                    atom_ids=["a1"],
                    text="runtime secret segment text",
                    original_range=TextRange(start=0, end=20),
                    locations=[],
                    segment_type="semantic",
                    ordinal=0,
                )
            ],
            atoms=[
                AnalysisAtom(
                    atom_id="a1",
                    input_id="input-1",
                    block_id="block-1",
                    text="raw atom secret value",
                    original_range=TextRange(start=0, end=20),
                    location=None,
                    atom_type="paragraph",
                    ordinal=0,
                )
            ],
            lexical_signals=[
                LexicalSignal(
                    signal_id="sig-1",
                    input_id="input-1",
                    block_id="block-1",
                    signal_type="secret_span",
                    pattern_id="secret",
                    match_basis="deterministic_regex",
                    normalized_range=TextRange(start=4, end=12),
                    original_range=TextRange(start=4, end=12),
                    severity_hint="critical",
                    deterministic=True,
                    value_fingerprint="fp_secret",
                    metadata={"raw_value": "do-not-persist"},
                )
            ],
            mapping_policy=SignalMappingPolicy(),
        )
    )

    dumped = str(result.model_dump())

    assert "do-not-persist" not in dumped
    assert "raw atom secret value" not in dumped
    assert "runtime secret segment text" not in dumped
    assert "fp_secret" in dumped


def test_safe_projection_excludes_raw_text_ranges_and_vectors():
    result = map_signals_to_segments(
        SignalMappingRequest(
            input_id="input-1",
            segments=[],
            atoms=[],
            lexical_signals=[],
            mapping_policy=SignalMappingPolicy(),
        )
    )

    metadata = project_signal_mapping_metadata(result)

    assert set(metadata) == {"input_id", "mapper_version", "segment_signal_sets", "failure"}
    assert "text" not in str(metadata)
    assert "vector" not in str(metadata)
    assert "original_range" not in str(metadata)


def test_mapper_does_not_emit_action_reason_or_notice_fields():
    result = map_signals_to_segments(
        SignalMappingRequest(
            input_id="input-1",
            segments=[],
            atoms=[],
            lexical_signals=[],
            mapping_policy=SignalMappingPolicy(),
        )
    )

    dumped = result.model_dump()

    assert "action" not in dumped
    assert "recommended_action" not in dumped
    assert "reason_code" not in dumped
    assert "user_notice" not in dumped
