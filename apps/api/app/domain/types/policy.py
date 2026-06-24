from typing import Literal

from pydantic import BaseModel, Field

from .common import ReasonCode


PolicyAction = Literal["allow", "warn", "mask", "block"]
PolicySeverity = Literal["info", "low", "medium", "high", "critical"]
ConfigurablePolicyAction = Literal["allow", "warn", "block"]
UnsupportedMaskFallbackAction = Literal["warn", "block"]


class PolicyActionSettings(BaseModel):
    context_classifier_action: ConfigurablePolicyAction = "warn"
    content_not_scanned_action: ConfigurablePolicyAction = "warn"
    parser_or_ocr_failure_action: ConfigurablePolicyAction = "warn"
    empty_input_action: ConfigurablePolicyAction = "allow"
    unsupported_mask_fallback_action: UnsupportedMaskFallbackAction = "block"


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
    action_settings: PolicyActionSettings = Field(default_factory=PolicyActionSettings)


class PolicyDecision(BaseModel):
    action: PolicyAction
    reason_code: ReasonCode
    severity: PolicySeverity
