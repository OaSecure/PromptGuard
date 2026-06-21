from typing import Literal

from pydantic import BaseModel, Field

from .common import ReasonCode


PolicyAction = Literal["allow", "warn", "mask", "block"]
PolicySeverity = Literal["info", "low", "medium", "high", "critical"]


class PolicyRuleEvidence(BaseModel):
    action: PolicyAction
    severity: PolicySeverity
    reason_code: ReasonCode = "INTERNAL_POLICY_REASON_UNMAPPED"
    masking_supported: bool = True


class PolicyInputEvidence(BaseModel):
    input_id: str
    content_scanned: bool


class PolicyMlEvidence(BaseModel):
    classifier_enabled: bool = False
    classifier_has_candidates: bool = False
    classifier_failed: bool = False
    verifier_failed: bool = False
    verifier_summary_present: bool = False


class PolicyDecisionRequest(BaseModel):
    request_id: str
    input_ids: list[str]
    evidence_codes: list[ReasonCode] = Field(default_factory=list)
    rules: list[PolicyRuleEvidence] = Field(default_factory=list)
    inputs: list[PolicyInputEvidence] = Field(default_factory=list)
    ml: PolicyMlEvidence = Field(default_factory=PolicyMlEvidence)


class PolicyDecision(BaseModel):
    action: PolicyAction
    reason_code: ReasonCode
    severity: PolicySeverity
