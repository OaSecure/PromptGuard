from typing import Protocol

from app.domain.types.policy import PolicyDecision, PolicyDecisionRequest


class PolicyOrchestratorPort(Protocol):
    def decide(self, request: PolicyDecisionRequest) -> PolicyDecision: ...
