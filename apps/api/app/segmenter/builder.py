import hashlib
import math

from app.atoms.models import AnalysisAtom, PipelineFailure, TextRange
from app.segmenter.models import (
    AdjacentBoundaryScore,
    AnalysisSegment,
    AtomEmbedding,
    SegmentBuildRequest,
    SegmentBuildResult,
    SegmentPolicy,
    SegmentType,
)

SEGMENTER_VERSION = "adjacent-semantic-segmenter-v1"
SEGMENT_ID_PREFIX_LENGTH = 16


def build_segments(request: SegmentBuildRequest) -> SegmentBuildResult:
    policy = request.segment_policy
    atoms = sorted(request.atoms, key=lambda atom: atom.ordinal)
    if not atoms:
        return SegmentBuildResult(
            input_id=request.input_id,
            segments=[],
            boundary_scores=[],
            segmenter_version=SEGMENTER_VERSION,
            failure=None,
        )

    embeddings_by_atom_id = {embedding.atom_id: embedding for embedding in request.atom_embeddings}
    embedding_failure = _validate_embeddings(atoms, embeddings_by_atom_id)
    if embedding_failure is not None:
        segments = _fallback_segments(request.input_id, atoms, policy, "structure")
        return SegmentBuildResult(
            input_id=request.input_id,
            segments=segments,
            boundary_scores=[],
            segmenter_version=SEGMENTER_VERSION,
            failure=embedding_failure,
        )

    if len(embeddings_by_atom_id) < len(atoms):
        segments = _fallback_segments(request.input_id, atoms, policy, "structure")
        return SegmentBuildResult(
            input_id=request.input_id,
            segments=segments,
            boundary_scores=[],
            segmenter_version=SEGMENTER_VERSION,
            failure=None,
        )

    try:
        boundary_scores = _boundary_scores(atoms, embeddings_by_atom_id, policy)
    except ValueError:
        segments = _fallback_segments(request.input_id, atoms, policy, "structure")
        return SegmentBuildResult(
            input_id=request.input_id,
            segments=segments,
            boundary_scores=[],
            segmenter_version=SEGMENTER_VERSION,
            failure=_embedding_failure("similarity_calculation_failed"),
        )
    boundary_indexes = _selected_boundary_indexes(atoms, boundary_scores, policy)
    boundary_indexes.update(_target_size_boundary_indexes(atoms, boundary_scores, boundary_indexes, policy))
    segments = _segments_from_boundaries(request.input_id, atoms, boundary_indexes, policy, "semantic")
    segments = _enforce_max_chars(request.input_id, segments, atoms, policy)

    return SegmentBuildResult(
        input_id=request.input_id,
        segments=segments,
        boundary_scores=boundary_scores,
        segmenter_version=SEGMENTER_VERSION,
        failure=None,
    )


def _validate_embeddings(
    atoms: list[AnalysisAtom],
    embeddings_by_atom_id: dict[str, AtomEmbedding],
) -> PipelineFailure | None:
    dimensions: set[int] = set()
    for atom in atoms:
        embedding = embeddings_by_atom_id.get(atom.atom_id)
        if embedding is None:
            continue
        vector = embedding.vector
        if not vector or any(not isinstance(value, int | float) or not math.isfinite(value) for value in vector):
            return _embedding_failure("invalid_embedding_vector")
        dimensions.add(len(vector))
    if len(dimensions) > 1:
        return _embedding_failure("invalid_embedding_vector")
    return None


def _embedding_failure(code: str) -> PipelineFailure:
    return PipelineFailure(code=code, message=code, metadata={"failure_code": code})


def _boundary_scores(
    atoms: list[AnalysisAtom],
    embeddings_by_atom_id: dict[str, AtomEmbedding],
    policy: SegmentPolicy,
) -> list[AdjacentBoundaryScore]:
    scores: list[AdjacentBoundaryScore] = []
    for left, right in zip(atoms, atoms[1:]):
        cosine = _cosine_similarity(embeddings_by_atom_id[left.atom_id].vector, embeddings_by_atom_id[right.atom_id].vector)
        selected = cosine < policy.cosine_break_threshold
        scores.append(
            AdjacentBoundaryScore(
                left_atom_id=left.atom_id,
                right_atom_id=right.atom_id,
                cosine_similarity=cosine,
                boundary_selected=selected,
            )
        )
    return scores


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("zero_vector")
    return dot / (left_norm * right_norm)


def _selected_boundary_indexes(
    atoms: list[AnalysisAtom],
    scores: list[AdjacentBoundaryScore],
    policy: SegmentPolicy,
) -> set[int]:
    boundaries: set[int] = set()
    for index, score in enumerate(scores):
        if score.boundary_selected and _boundary_respects_min_atoms(index, boundaries, len(atoms), policy.min_atoms):
            boundaries.add(index)
        if policy.respect_block_boundary and atoms[index].block_id != atoms[index + 1].block_id:
            if _boundary_respects_min_atoms(index, boundaries, len(atoms), policy.min_atoms):
                boundaries.add(index)
    return boundaries


def _target_size_boundary_indexes(
    atoms: list[AnalysisAtom],
    scores: list[AdjacentBoundaryScore],
    existing_boundaries: set[int],
    policy: SegmentPolicy,
) -> set[int]:
    extra: set[int] = set()
    start = 0
    for end in sorted(existing_boundaries | {len(atoms) - 1}):
        group = atoms[start : end + 1]
        if sum(len(atom.text) for atom in group) > policy.target_chars and len(group) > policy.min_atoms:
            candidates = [
                (start + offset, scores[start + offset].cosine_similarity)
                for offset in range(len(group) - 1)
                if start + offset not in existing_boundaries
            ]
            if candidates:
                extra.add(min(candidates, key=lambda item: (item[1], item[0]))[0])
        start = end + 1
    return extra


def _boundary_respects_min_atoms(index: int, boundaries: set[int], atom_count: int, min_atoms: int) -> bool:
    previous = max(boundaries) if boundaries else -1
    left_count = index - previous
    right_count = atom_count - index - 1
    return left_count >= min_atoms and right_count >= min_atoms


def _segments_from_boundaries(
    input_id: str,
    atoms: list[AnalysisAtom],
    boundary_indexes: set[int],
    policy: SegmentPolicy,
    default_type: SegmentType,
) -> list[AnalysisSegment]:
    groups: list[list[AnalysisAtom]] = []
    start = 0
    for index in sorted(boundary_indexes):
        groups.append(atoms[start : index + 1])
        start = index + 1
    groups.append(atoms[start:])
    return [_build_segment(input_id, group, ordinal, _segment_type_for_group(group, default_type), policy) for ordinal, group in enumerate(groups)]


def _fallback_segments(
    input_id: str,
    atoms: list[AnalysisAtom],
    policy: SegmentPolicy,
    default_type: SegmentType,
) -> list[AnalysisSegment]:
    if policy.respect_block_boundary:
        boundaries = {index for index, (left, right) in enumerate(zip(atoms, atoms[1:])) if left.block_id != right.block_id}
    else:
        boundaries = set()
    segments = _segments_from_boundaries(input_id, atoms, boundaries, policy, default_type)
    return _enforce_max_chars(input_id, segments, atoms, policy)


def _enforce_max_chars(
    input_id: str,
    segments: list[AnalysisSegment],
    atoms: list[AnalysisAtom],
    policy: SegmentPolicy,
) -> list[AnalysisSegment]:
    atoms_by_id = {atom.atom_id: atom for atom in atoms}
    resized: list[AnalysisSegment] = []
    for segment in segments:
        if len(segment.text) <= policy.max_chars:
            resized.append(segment)
            continue
        current: list[AnalysisAtom] = []
        current_length = 0
        for atom_id in segment.atom_ids:
            atom = atoms_by_id[atom_id]
            if current and current_length + len(atom.text) > policy.max_chars:
                resized.append(_build_segment(input_id, current, len(resized), "size_fallback", policy))
                current = []
                current_length = 0
            current.append(atom)
            current_length += len(atom.text)
        if current:
            resized.append(_build_segment(input_id, current, len(resized), "size_fallback", policy))

    return [_build_segment(input_id, [atoms_by_id[atom_id] for atom_id in segment.atom_ids], ordinal, segment.segment_type, policy) for ordinal, segment in enumerate(resized)]


def _segment_type_for_group(group: list[AnalysisAtom], default_type: SegmentType) -> SegmentType:
    if len(group) == 1:
        return "single_atom"
    return default_type


def _build_segment(
    input_id: str,
    atoms: list[AnalysisAtom],
    ordinal: int,
    segment_type: SegmentType,
    policy: SegmentPolicy,
) -> AnalysisSegment:
    atom_ids = [atom.atom_id for atom in atoms]
    return AnalysisSegment(
        segment_id=_make_segment_id(input_id, atom_ids, ordinal, SEGMENT_ID_PREFIX_LENGTH),
        input_id=input_id,
        atom_ids=atom_ids,
        text="".join(atom.text for atom in atoms),
        original_range=_segment_original_range(atoms),
        locations=_locations(atoms),
        segment_type=segment_type,
        ordinal=ordinal,
    )


def _segment_original_range(atoms: list[AnalysisAtom]) -> TextRange:
    return TextRange(
        start=min(atom.original_range.start for atom in atoms),
        end=max(atom.original_range.end for atom in atoms),
    )


def _locations(atoms: list[AnalysisAtom]) -> list[object]:
    locations: list[object] = []
    seen: set[str] = set()
    for atom in atoms:
        if atom.location is None:
            continue
        marker = repr(atom.location)
        if marker not in seen:
            seen.add(marker)
            locations.append(atom.location)
    return locations


def _make_segment_id(input_id: str, atom_ids: list[str], ordinal: int, prefix_length: int) -> str:
    digest = hashlib.sha256(f"{input_id}:{atom_ids[0]}:{atom_ids[-1]}:{ordinal}".encode("utf-8")).hexdigest()
    return f"seg_{digest[:prefix_length]}"
