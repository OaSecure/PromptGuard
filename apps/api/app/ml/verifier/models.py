from collections.abc import Mapping
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.atoms.models import PipelineFailure
from app.ml.classifier.models import SegmentClassificationCandidate, SegmentClassificationResult

RobertaVerificationStatus = Literal["confirmed", "rejected", "uncertain", "timeout", "failed"]


class VerifierArtifactRef(BaseModel):
    artifact_id: str
    model_version: str
    runtime_version: str

    @field_validator("artifact_id", "model_version", "runtime_version")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_verifier_artifact_field", "verifier artifact field must not be blank")
        return value


class RobertaVerificationCandidate(BaseModel):
    segment_id: str
    candidate_label: str
    classifier_artifact_id: str | None = None
    classifier_runtime_version: str | None = None
    text: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator("segment_id", "candidate_label")
    @classmethod
    def required_candidate_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_verifier_candidate_field", "verifier candidate field must not be blank")
        return value

    @classmethod
    def from_classifier_candidate(cls, candidate: SegmentClassificationCandidate, *, text: str | None = None) -> "RobertaVerificationCandidate":
        return cls(
            segment_id=candidate.segment_id,
            candidate_label=candidate.label,
            classifier_artifact_id=candidate.artifact_id,
            classifier_runtime_version=candidate.runtime_version,
            text=text,
        )


class RobertaVerificationRequest(BaseModel):
    input_id: str
    candidates: list[RobertaVerificationCandidate] = Field(default_factory=list)
    artifact: VerifierArtifactRef
    timeout_ms: int = Field(default=3000, ge=1)

    @field_validator("input_id")
    @classmethod
    def input_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_input_id", "input_id must not be blank")
        return value


class RobertaVerificationEvidence(BaseModel):
    segment_id: str
    candidate_label: str
    verifier_status: RobertaVerificationStatus
    accepted: bool
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_code_candidates: list[str] = Field(default_factory=list)
    verifier_model_version: str
    failure: PipelineFailure | None = None

    @field_validator("segment_id", "candidate_label", "verifier_model_version")
    @classmethod
    def required_evidence_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_verifier_evidence_field", "verifier evidence field must not be blank")
        return value

    @model_validator(mode="after")
    def accepted_only_when_confirmed(self) -> "RobertaVerificationEvidence":
        if self.accepted and self.verifier_status != "confirmed":
            raise PydanticCustomError("verifier_accepts_unconfirmed", "verifier may accept only confirmed evidence")
        return self


class RobertaVerificationResult(BaseModel):
    input_id: str
    verifications: list[RobertaVerificationEvidence] = Field(default_factory=list)
    failure: PipelineFailure | None = None

    @field_validator("input_id")
    @classmethod
    def input_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_input_id", "input_id must not be blank")
        return value

    @model_validator(mode="after")
    def failure_must_fail_closed(self) -> "RobertaVerificationResult":
        if self.failure is not None and self.verifications:
            raise PydanticCustomError("verifier_failure_with_results", "verifier failures must not include verification results")
        return self


class VerifierModelPort(Protocol):
    def verify(self, request: RobertaVerificationRequest) -> RobertaVerificationResult:
        ...


def build_verification_request_from_classifier(
    *,
    input_id: str,
    classification: SegmentClassificationResult,
    artifact: VerifierArtifactRef,
    timeout_ms: int = 3000,
    candidate_text_by_segment_id: Mapping[str, str] | None = None,
) -> RobertaVerificationRequest:
    if classification.failure is not None:
        raise ValueError("classifier failure cannot create verifier request")
    return RobertaVerificationRequest(
        input_id=input_id,
        candidates=[
            RobertaVerificationCandidate.from_classifier_candidate(
                candidate,
                text=candidate_text_by_segment_id.get(candidate.segment_id) if candidate_text_by_segment_id is not None else None,
            )
            for candidate in classification.candidates
        ],
        artifact=artifact,
        timeout_ms=timeout_ms,
    )

