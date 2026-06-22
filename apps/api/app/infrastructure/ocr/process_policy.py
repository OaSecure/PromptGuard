from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .process_port import OcrProcessRequest


@dataclass(frozen=True)
class ProcessExecutionPolicy:
    allowed_environment_keys: frozenset[str]
    environment: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))


def safe_environment(policy: ProcessExecutionPolicy) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value) for key, value in policy.environment.items() if key in policy.allowed_environment_keys))


def request_satisfies_policy(request: OcrProcessRequest) -> bool:
    checks = (
        isinstance(request.argv, tuple)
        and bool(request.argv),
        _valid_argv(request.argv),
        request.shell is False,
        request.allow_network_fallback is False,
        request.allow_automatic_download is False,
        request.timeout_ms > 0,
        request.max_input_bytes > 0,
        request.max_output_bytes > 0,
    )
    return all(checks)


def _valid_argv(argv: object) -> bool:
    return isinstance(argv, tuple) and all(isinstance(argument, str) and bool(argument) for argument in argv)
