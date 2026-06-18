from typing import Any, Literal

from pydantic import BaseModel, Field

from app.atoms.models import AnalysisAtom, PipelineFailure, TextRange
from app.segmenter.models import AnalysisSegment

SignalType = Literal[
    "pii_span",
    "secret_span",
    "secret_fingerprint",
    "token_candidate",
    "protected_target_hit",
    "custom_regex_hit",
    "sensitive_value_pattern_hit",
    "context_trigger_hit",
]
MatchBasis = Literal[
    "deterministic_regex",
    "heuristic_regex",
    "keyword",
    "protected_target",
    "fingerprint",
    "context_trigger",
]
SeverityHint = Literal["info", "low", "medium", "high", "critical"]
SignalMappingBasis = Literal["offset_overlap", "atom_membership"]


class LexicalSignal(BaseModel):
    signal_id: str
    input_id: str
    block_id: str
    signal_type: SignalType
    pattern_id: str
    match_basis: MatchBasis
    normalized_range: TextRange
    original_range: TextRange
    severity_hint: SeverityHint
    deterministic: bool
    value_fingerprint: str | None
    protected_target_hit: bool = False
    protected_target_id: str | None = None
    protected_target_type: str | None = None
    protected_target_registry_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalMappingPolicy(BaseModel):
    allow_multiple_segment_matches: bool = False
    mapper_version: str = "signal-to-segment-mapper-v1"


class SignalMappingRequest(BaseModel):
    input_id: str
    segments: list[AnalysisSegment]
    atoms: list[AnalysisAtom]
    lexical_signals: list[LexicalSignal]
    mapping_policy: SignalMappingPolicy


class MappedSignal(BaseModel):
    signal_id: str
    signal_type: SignalType
    pattern_id: str
    match_basis: MatchBasis
    severity_hint: SeverityHint
    deterministic: bool
    value_fingerprint: str | None
    protected_target_hit: bool
    protected_target_id: str | None
    protected_target_type: str | None
    protected_target_registry_version: str | None
    atom_ids: list[str]
    mapping_basis: SignalMappingBasis


class SegmentSignalSet(BaseModel):
    segment_id: str
    signal_ids: list[str]
    signals: list[MappedSignal]
    max_severity: SeverityHint | None
    signal_count: int


class SignalMappingResult(BaseModel):
    input_id: str
    segment_signal_sets: list[SegmentSignalSet]
    mapper_version: str
    failure: PipelineFailure | None = None
