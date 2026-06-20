from typing import Literal

from pydantic import BaseModel, Field

from .common import PipelineFailure


class AtomEmbeddingResult(BaseModel):
    input_id: str
    atom_ids: list[str]
    model_id: str
    failure: PipelineFailure | None = None


class SegmentClassificationCandidate(BaseModel):
    segment_id: str
    label: str
    score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)


class VerifierResult(BaseModel):
    segment_id: str
    label: str
    status: Literal["confirmed", "rejected", "uncertain", "timeout", "failed"]
    model_id: str
    failure: PipelineFailure | None = None
