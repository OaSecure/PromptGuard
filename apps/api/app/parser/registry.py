from dataclasses import dataclass

from app.parser.models import (
    ParserAdapterCapability,
    ParserBoundaryError,
    StepKind,
    sanitized_failure,
)
from app.parser.ports import ParserStepAdapterPort


@dataclass(frozen=True)
class ParserAdapterRegistration:
    capability: ParserAdapterCapability
    adapter: ParserStepAdapterPort


class InMemoryParserAdapterRegistry:
    def __init__(self, registrations: tuple[ParserAdapterRegistration, ...]) -> None:
        self._registrations: dict[str, ParserAdapterRegistration] = {}
        for registration in registrations:
            capability_id = registration.capability.capability_id
            if capability_id in self._registrations:
                raise ValueError("duplicate capability id")
            self._registrations[capability_id] = registration

    def resolve_adapter(self, capability_id: str, step_kind: StepKind) -> ParserStepAdapterPort:
        registration = self._registrations.get(capability_id)
        if registration is None or step_kind not in registration.capability.step_kinds:
            raise ParserBoundaryError(sanitized_failure("UNSUPPORTED_FILE_KIND"))
        if not registration.capability.enabled:
            raise ParserBoundaryError(sanitized_failure("PARSER_DISABLED"))
        if not registration.capability.license_allowed:
            raise ParserBoundaryError(sanitized_failure("LICENSE_POLICY_VIOLATION"))
        return registration.adapter
