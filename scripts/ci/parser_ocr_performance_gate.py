"""Opt-in entry point for deterministic parser/OCR performance contracts."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ALLOWED_PROFILE = "synthetic"
PERFORMANCE_TEST_TARGETS = (
    "tests/performance/parser_ocr/test_synthetic_performance_contract.py",
    "tests/performance/parser_ocr/test_synthetic_performance_privacy.py",
    "tests/performance/parser_ocr/test_performance_report_schema.py",
)
PROFILE_ENVIRONMENT_VARIABLE = "PARSER_OCR_PERFORMANCE_PROFILE"
API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class GateOutcome:
    exit_code: int
    message: str


Runner = Callable[[tuple[str, ...]], CommandResult]


def run_gate(profile: str | None, runner: Runner) -> GateOutcome:
    if profile is None or profile == "":
        return GateOutcome(0, "parser/ocr synthetic performance gate skipped")
    if profile != ALLOWED_PROFILE:
        return GateOutcome(2, "parser/ocr performance profile is not allowed")
    command = ("python", "-m", "pytest", *PERFORMANCE_TEST_TARGETS, "--tb=no", "-q")
    completed = runner(command)
    if completed.returncode != 0:
        return GateOutcome(1, "parser/ocr synthetic performance gate failed")
    return GateOutcome(0, "parser/ocr synthetic performance gate passed")


def _run(command: tuple[str, ...]) -> CommandResult:
    completed = subprocess.run(command, cwd=API_ROOT, capture_output=True, text=True, check=False)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def main() -> int:
    outcome = run_gate(os.environ.get(PROFILE_ENVIRONMENT_VARIABLE), _run)
    print(outcome.message)
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
