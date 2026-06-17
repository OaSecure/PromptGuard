from typing import Literal

from pydantic import BaseModel

from app.atoms.models import AnalysisAtom, PipelineFailure, TextRange

SegmentType = Literal["semantic", "structure", "size_fallback", "single_atom"]


class AtomEmbedding(BaseModel):
    atom_id: str
    vector: list[float]


class SegmentPolicy(BaseModel):
    min_atoms: int = 1
    target_chars: int = 1800
    max_chars: int = 3200
    cosine_break_threshold: float = 0.72
    respect_block_boundary: bool = True


class SegmentBuildRequest(BaseModel):
    input_id: str
    atoms: list[AnalysisAtom]
    atom_embeddings: list[AtomEmbedding]
    segment_policy: SegmentPolicy


class AdjacentBoundaryScore(BaseModel):
    left_atom_id: str
    right_atom_id: str
    cosine_similarity: float
    boundary_selected: bool


class AnalysisSegment(BaseModel):
    segment_id: str
    input_id: str
    atom_ids: list[str]
    text: str
    original_range: TextRange
    locations: list[object]
    segment_type: SegmentType
    ordinal: int


class SegmentBuildResult(BaseModel):
    input_id: str
    segments: list[AnalysisSegment]
    boundary_scores: list[AdjacentBoundaryScore]
    segmenter_version: str
    failure: PipelineFailure | None = None
