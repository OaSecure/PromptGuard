from typing import Protocol

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.atoms.models import PipelineFailure
from app.ml.segment_embedding.models import SegmentEmbedding


class ClassifierArtifactRef(BaseModel):
    artifact_id: str
    manifest_version: str
    runtime_version: str
    target_labels: list[str]
    candidate_threshold: float = Field(ge=0.0, le=1.0)
    embedding_model_version: str

    @field_validator("artifact_id", "manifest_version", "runtime_version", "embedding_model_version")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_classifier_artifact_field", "classifier artifact field must not be blank")
        return value

    @field_validator("target_labels")
    @classmethod
    def target_labels_must_be_unique(cls, value: list[str]) -> list[str]:
        if not value:
            raise PydanticCustomError("missing_classifier_labels", "classifier target labels must not be empty")
        if any(not label.strip() for label in value):
            raise PydanticCustomError("blank_classifier_label", "classifier target labels must not be blank")
        if len(set(value)) != len(value):
            raise PydanticCustomError("duplicate_classifier_label", "classifier target labels must be unique")
        return value


class SegmentClassificationRequest(BaseModel):
    input_id: str
    segment_embeddings: list[SegmentEmbedding]
    artifact: ClassifierArtifactRef

    @field_validator("input_id")
    @classmethod
    def input_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_input_id", "input_id must not be blank")
        return value


class SegmentClassificationCandidate(BaseModel):
    segment_id: str
    label: str
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    artifact_id: str
    runtime_version: str


class SegmentClassificationResult(BaseModel):
    input_id: str
    candidates: list[SegmentClassificationCandidate] = Field(default_factory=list)
    failure: PipelineFailure | None = None

    @model_validator(mode="after")
    def failure_must_fail_closed(self) -> "SegmentClassificationResult":
        if self.failure is not None and self.candidates:
            raise PydanticCustomError("classifier_failure_with_candidates", "classifier failures must not include candidates")
        return self


class ProbabilityPredictor(Protocol):
    target_labels: list[str]

    def predict_probabilities(self, vectors: list[list[float]]) -> list[list[float]]:
        ...
