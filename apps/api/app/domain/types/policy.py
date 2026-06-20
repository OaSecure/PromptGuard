from typing import Literal

from pydantic import BaseModel, Field

from .common import ReasonCode


class PolicyDecisionRequest(BaseModel):
    request_id: str
    input_ids: list[str]
    evidence_codes: list[ReasonCode] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    action: Literal["allow", "warn", "mask", "block"]
    reason_code: ReasonCode
    severity: Literal["info", "low", "medium", "high", "critical"]
