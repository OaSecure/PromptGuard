from collections.abc import Iterable

from app.atoms.models import AnalysisAtom, TextRange
from app.mapping.models import (
    LexicalSignal,
    MappedSignal,
    SegmentSignalSet,
    SignalMappingBasis,
    SignalMappingRequest,
    SignalMappingResult,
)
from app.segmenter.models import AnalysisSegment

SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def map_signals_to_segments(request: SignalMappingRequest) -> SignalMappingResult:
    atoms_by_id = {atom.atom_id: atom for atom in request.atoms}
    signals = _dedupe_signals_by_id(
        signal for signal in request.lexical_signals if signal.input_id == request.input_id
    )
    assigned_signal_ids: set[str] = set()
    signal_sets: list[SegmentSignalSet] = []
    for segment in request.segments:
        signal_set = _map_segment_signals(
            segment,
            signals,
            atoms_by_id,
            request.mapping_policy.allow_multiple_segment_matches,
            assigned_signal_ids,
        )
        signal_sets.append(signal_set)

    return SignalMappingResult(
        input_id=request.input_id,
        segment_signal_sets=signal_sets,
        mapper_version=request.mapping_policy.mapper_version,
        failure=None,
    )


def _dedupe_signals_by_id(signals: Iterable[LexicalSignal]) -> list[LexicalSignal]:
    deduped: list[LexicalSignal] = []
    seen: set[str] = set()
    for signal in signals:
        if signal.signal_id in seen:
            continue
        seen.add(signal.signal_id)
        deduped.append(signal)
    return deduped


def _map_segment_signals(
    segment: AnalysisSegment,
    signals: list[LexicalSignal],
    atoms_by_id: dict[str, AnalysisAtom],
    allow_multiple: bool,
    assigned_signal_ids: set[str],
) -> SegmentSignalSet:
    segment_atoms = [atoms_by_id[atom_id] for atom_id in segment.atom_ids if atom_id in atoms_by_id]
    mapped: list[MappedSignal] = []
    for signal in signals:
        if not allow_multiple and signal.signal_id in assigned_signal_ids:
            continue
        if not _is_valid_signal_range(signal.original_range):
            continue
        mapped_signal = _map_signal_to_segment(signal, segment, segment_atoms)
        if mapped_signal is not None:
            mapped.append(mapped_signal)
            assigned_signal_ids.add(signal.signal_id)

    return SegmentSignalSet(
        segment_id=segment.segment_id,
        signal_ids=[signal.signal_id for signal in mapped],
        signals=mapped,
        max_severity=_max_severity(mapped),
        signal_count=len(mapped),
    )


def _map_signal_to_segment(
    signal: LexicalSignal,
    segment: AnalysisSegment,
    segment_atoms: list[AnalysisAtom],
) -> MappedSignal | None:
    overlapping_atoms = [
        atom
        for atom in segment_atoms
        if atom.block_id == signal.block_id and _ranges_overlap(atom.original_range, signal.original_range)
    ]
    if not overlapping_atoms:
        return None

    if _can_use_segment_offset_overlap(signal, segment, segment_atoms):
        basis = "offset_overlap"
    else:
        basis = "atom_membership"

    return _mapped_signal(signal, [atom.atom_id for atom in overlapping_atoms], basis)


def _can_use_segment_offset_overlap(
    signal: LexicalSignal,
    segment: AnalysisSegment,
    segment_atoms: list[AnalysisAtom],
) -> bool:
    if not _ranges_overlap(segment.original_range, signal.original_range):
        return False
    segment_block_ids = {atom.block_id for atom in segment_atoms}
    return segment_block_ids == {signal.block_id}


def _mapped_signal(signal: LexicalSignal, atom_ids: list[str], basis: SignalMappingBasis) -> MappedSignal:
    return MappedSignal(
        signal_id=signal.signal_id,
        signal_type=signal.signal_type,
        pattern_id=signal.pattern_id,
        match_basis=signal.match_basis,
        severity_hint=signal.severity_hint,
        deterministic=signal.deterministic,
        value_fingerprint=signal.value_fingerprint,
        protected_target_hit=signal.protected_target_hit,
        protected_target_id=signal.protected_target_id,
        protected_target_type=signal.protected_target_type,
        protected_target_registry_version=signal.protected_target_registry_version,
        atom_ids=atom_ids,
        mapping_basis=basis,
    )


def _is_valid_signal_range(text_range: TextRange) -> bool:
    return text_range.start < text_range.end


def _ranges_overlap(left: TextRange, right: TextRange) -> bool:
    return left.start < right.end and right.start < left.end


def _max_severity(signals: list[MappedSignal]) -> str | None:
    if not signals:
        return None
    return max((signal.severity_hint for signal in signals), key=lambda severity: SEVERITY_ORDER[severity])
