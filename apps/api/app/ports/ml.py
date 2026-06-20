from typing import Protocol

from app.domain.types.analysis import AnalysisAtom, AnalysisSegment
from app.domain.types.ml import AtomEmbeddingResult, SegmentClassificationCandidate, VerifierResult


class EmbeddingModelPort(Protocol):
    def embed(self, input_id: str, atoms: list[AnalysisAtom]) -> AtomEmbeddingResult: ...
class ClassifierArtifactRegistry(Protocol):
    def artifact_ref(self, model_id: str) -> str: ...
class SegmentClassifierPort(Protocol):
    def classify(self, segments: list[AnalysisSegment]) -> list[SegmentClassificationCandidate]: ...
class VerifierModelPort(Protocol):
    def verify(self, candidates: list[SegmentClassificationCandidate]) -> list[VerifierResult]: ...
