from app.atoms import AnalysisAtom, TextRange
from app.mapping import (
    LexicalSignal,
    SignalMappingPolicy,
    SignalMappingRequest,
    map_signals_to_segments,
)
from app.segmenter import AnalysisSegment


def atom(atom_id: str, block_id: str, start: int, end: int, ordinal: int) -> AnalysisAtom:
    return AnalysisAtom(
        atom_id=atom_id,
        input_id="input-1",
        block_id=block_id,
        text="x" * (end - start),
        original_range=TextRange(start=start, end=end),
        location=None,
        atom_type="paragraph",
        ordinal=ordinal,
    )


def segment(segment_id: str, atom_ids: list[str], start: int, end: int, ordinal: int) -> AnalysisSegment:
    return AnalysisSegment(
        segment_id=segment_id,
        input_id="input-1",
        atom_ids=atom_ids,
        text="runtime segment text",
        original_range=TextRange(start=start, end=end),
        locations=[],
        segment_type="semantic",
        ordinal=ordinal,
    )


def signal(signal_id: str, block_id: str, start: int, end: int) -> LexicalSignal:
    return LexicalSignal(
        signal_id=signal_id,
        input_id="input-1",
        block_id=block_id,
        signal_type="pii_span",
        pattern_id="email",
        match_basis="deterministic_regex",
        normalized_range=TextRange(start=start, end=end),
        original_range=TextRange(start=start, end=end),
        severity_hint="high",
        deterministic=True,
        value_fingerprint="fp_123",
    )


def request(
    segments: list[AnalysisSegment],
    atoms: list[AnalysisAtom],
    signals: list[LexicalSignal],
    policy: SignalMappingPolicy | None = None,
) -> SignalMappingRequest:
    return SignalMappingRequest(
        input_id="input-1",
        segments=segments,
        atoms=atoms,
        lexical_signals=signals,
        mapping_policy=policy or SignalMappingPolicy(),
    )


def test_offset_overlap_maps_signal_to_segment():
    result = map_signals_to_segments(
        request(
            [segment("seg-1", ["a1"], 0, 20, 0)],
            [atom("a1", "block-1", 0, 20, 0)],
            [signal("sig-1", "block-1", 5, 10)],
        )
    )

    assert result.failure is None
    assert result.segment_signal_sets[0].segment_id == "seg-1"
    assert [item.signal_id for item in result.segment_signal_sets[0].signals] == ["sig-1"]
    assert result.segment_signal_sets[0].signals[0].mapping_basis == "offset_overlap"


def test_atom_membership_resolves_cross_block_segment_mapping():
    result = map_signals_to_segments(
        request(
            [segment("seg-1", ["a1", "a2"], 0, 10, 0)],
            [
                atom("a1", "block-1", 0, 10, 0),
                atom("a2", "block-2", 0, 10, 1),
            ],
            [signal("sig-1", "block-2", 3, 5)],
        )
    )

    assert result.failure is None
    assert [item.signal_id for item in result.segment_signal_sets[0].signals] == ["sig-1"]
    assert result.segment_signal_sets[0].signals[0].atom_ids == ["a2"]
    assert result.segment_signal_sets[0].signals[0].mapping_basis == "atom_membership"


def test_mapper_is_deterministic_and_preserves_segment_order():
    segments = [
        segment("seg-2", ["a2"], 20, 40, 1),
        segment("seg-1", ["a1"], 0, 20, 0),
    ]
    atoms = [atom("a1", "block-1", 0, 20, 0), atom("a2", "block-1", 20, 40, 1)]
    signals = [signal("sig-2", "block-1", 25, 30), signal("sig-1", "block-1", 5, 10)]

    first = map_signals_to_segments(request(segments, atoms, signals))
    second = map_signals_to_segments(request(segments, atoms, signals))

    assert [item.segment_id for item in first.segment_signal_sets] == ["seg-2", "seg-1"]
    assert first.model_dump() == second.model_dump()


def test_no_signals_returns_empty_signal_sets():
    result = map_signals_to_segments(
        request(
            [segment("seg-1", ["a1"], 0, 20, 0)],
            [atom("a1", "block-1", 0, 20, 0)],
            [],
        )
    )

    assert result.failure is None
    assert [item.model_dump() for item in result.segment_signal_sets] == [
        {
            "segment_id": "seg-1",
            "signal_ids": [],
            "signals": [],
            "max_severity": None,
            "signal_count": 0,
        }
    ]


def test_invalid_range_signal_is_skipped_without_raw_text_failure():
    result = map_signals_to_segments(
        request(
            [segment("seg-1", ["a1"], 0, 20, 0)],
            [atom("a1", "block-1", 0, 20, 0)],
            [signal("sig-1", "block-1", 10, 10)],
        )
    )

    assert result.segment_signal_sets[0].signals == []
    assert result.failure is None


def test_signal_mapping_result_uses_singular_failure_field():
    result = map_signals_to_segments(request([], [], []))

    dumped = result.model_dump()
    assert "failure" in dumped
    assert "failures" not in dumped


def test_half_open_touching_ranges_do_not_overlap():
    result = map_signals_to_segments(
        request(
            [segment("seg-1", ["a1"], 0, 10, 0)],
            [atom("a1", "block-1", 0, 10, 0)],
            [signal("sig-1", "block-1", 10, 15)],
        )
    )

    assert result.segment_signal_sets[0].signals == []


def test_signal_maps_to_first_segment_only_by_default_when_boundaries_overlap():
    shared = signal("sig-1", "block-1", 8, 12)
    result = map_signals_to_segments(
        request(
            [
                segment("seg-1", ["a1"], 0, 10, 0),
                segment("seg-2", ["a2"], 10, 20, 1),
            ],
            [atom("a1", "block-1", 0, 12, 0), atom("a2", "block-1", 8, 20, 1)],
            [shared],
        )
    )

    assert [item.signal_ids for item in result.segment_signal_sets] == [["sig-1"], []]


def test_signal_can_map_to_multiple_segments_when_policy_allows():
    result = map_signals_to_segments(
        request(
            [
                segment("seg-1", ["a1"], 0, 10, 0),
                segment("seg-2", ["a2"], 10, 20, 1),
            ],
            [atom("a1", "block-1", 0, 12, 0), atom("a2", "block-1", 8, 20, 1)],
            [signal("sig-1", "block-1", 8, 12)],
            SignalMappingPolicy(allow_multiple_segment_matches=True),
        )
    )

    assert [item.signal_ids for item in result.segment_signal_sets] == [["sig-1"], ["sig-1"]]


def test_signal_with_different_input_id_is_not_mapped():
    foreign_signal = signal("sig-foreign", "block-1", 5, 10)
    foreign_signal.input_id = "other-input"

    result = map_signals_to_segments(
        request(
            [segment("seg-1", ["a1"], 0, 20, 0)],
            [atom("a1", "block-1", 0, 20, 0)],
            [foreign_signal],
        )
    )

    assert result.segment_signal_sets[0].signals == []


def test_duplicate_signal_ids_are_deduplicated_per_segment():
    first = signal("sig-1", "block-1", 5, 10)
    duplicate = signal("sig-1", "block-1", 6, 11)

    result = map_signals_to_segments(
        request(
            [segment("seg-1", ["a1"], 0, 20, 0)],
            [atom("a1", "block-1", 0, 20, 0)],
            [first, duplicate],
        )
    )

    assert result.segment_signal_sets[0].signal_ids == ["sig-1"]
    assert result.segment_signal_sets[0].signal_count == 1
