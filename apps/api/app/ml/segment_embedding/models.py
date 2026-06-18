from typing import Literal

from pydantic import BaseModel

from app.atoms.models import PipelineFailure
from app.ml.embedding.models import AtomEmbedding
from app.segmenter.models import AnalysisSegment

SegmentEmbeddingPooling = Literal["mean", "weighted_mean"]


class SegmentEmbeddingPolicy(BaseModel):
    pooling: SegmentEmbeddingPooling = "mean"
    normalize_vectors: bool = True


class SegmentEmbeddingBuildRequest(BaseModel):
    input_id: str
    segments: list[AnalysisSegment]
    atom_embeddings: list[AtomEmbedding]
    embedding_model_version: str
    policy: SegmentEmbeddingPolicy


class SegmentEmbedding(BaseModel):
    segment_id: str
    vector: list[float]
    embedding_model_version: str
    dimension: int
    pooling: SegmentEmbeddingPooling
    normalized: bool


class SegmentEmbeddingBuildResult(BaseModel):
    input_id: str
    segment_embeddings: list[SegmentEmbedding]
    failure: PipelineFailure | None = None
