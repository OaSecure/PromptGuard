from pathlib import Path

import pytest

from scripts.ci.parser_ocr_performance_gate import (
    ALLOWED_PROFILE,
    PERFORMANCE_TEST_TARGETS,
    CommandResult,
    run_gate,
)

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
ENTRY_POINT = ROOT / "scripts" / "ci" / "parser_ocr_performance_gate.py"


class RecordingRunner:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command: tuple[str, ...]) -> CommandResult:
        self.calls.append(command)
        return CommandResult(self.returncode, self.stdout, self.stderr)


@pytest.mark.parametrize("profile", [None, ""])
def test_missing_or_empty_opt_in_skips_without_running_profile(profile):
    runner = RecordingRunner()

    result = run_gate(profile, runner)

    assert result.exit_code == 0
    assert result.message == "parser/ocr synthetic performance gate skipped"
    assert runner.calls == []


def test_allowed_opt_in_selects_only_pr11a_pr11b_synthetic_suite():
    runner = RecordingRunner()

    result = run_gate(ALLOWED_PROFILE, runner)

    assert result.exit_code == 0
    assert result.message == "parser/ocr synthetic performance gate passed"
    assert runner.calls == [
        (
            "python",
            "-m",
            "pytest",
            *PERFORMANCE_TEST_TARGETS,
            "--tb=no",
            "-q",
        )
    ]
    assert PERFORMANCE_TEST_TARGETS == (
        "tests/performance/parser_ocr/test_synthetic_performance_contract.py",
        "tests/performance/parser_ocr/test_synthetic_performance_privacy.py",
        "tests/performance/parser_ocr/test_performance_report_schema.py",
    )


@pytest.mark.parametrize("profile", ["real", "heavy", "unknown", "synthetic "])
def test_unknown_profile_fails_closed_without_running_profile(profile):
    runner = RecordingRunner()

    result = run_gate(profile, runner)

    assert result.exit_code == 2
    assert result.message == "parser/ocr performance profile is not allowed"
    assert runner.calls == []


def test_failure_output_is_sanitized_and_does_not_forward_captured_streams():
    sensitive = ":".join(
        (
            "PRIVATE_RAW_BYTES",
            "/PRIVATE_TEMP_PATH",
            "PRIVATE_ORIGINAL_FILENAME",
            "PRIVATE_OCR_TEXT",
            "PRIVATE_EXTRACTED_TEXT",
            "PRIVATE_PARTIAL_OUTPUT",
            "PRIVATE_STDOUT",
            "PRIVATE_STDERR",
            "PRIVATE_RAW_EXCEPTION",
            "987654321",
        )
    )
    runner = RecordingRunner(returncode=1, stdout=sensitive, stderr=sensitive)

    result = run_gate(ALLOWED_PROFILE, runner)

    assert result.exit_code == 1
    assert result.message == "parser/ocr synthetic performance gate failed"
    assert sensitive not in result.message
    assert "987654321" not in result.message


def test_workflow_exposes_only_the_synthetic_opt_in_profile():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "parser_ocr_performance_profile:" in workflow
    assert "options:" in workflow
    assert "- disabled" in workflow
    assert "- synthetic" in workflow
    assert "PARSER_OCR_PERFORMANCE_PROFILE" in workflow
    assert "python scripts/ci/parser_ocr_performance_gate.py" in workflow


def test_entry_point_and_opt_in_step_contain_no_forbidden_commands():
    entry_point = ENTRY_POINT.read_text(encoding="utf-8").casefold()
    workflow = WORKFLOW.read_text(encoding="utf-8").casefold()
    opt_in_step = workflow.split("run parser/ocr synthetic performance gate", 1)[1]
    forbidden = (
        "tesseract ",
        "paddleocr ",
        "traineddata",
        "model download",
        "pip install",
        "docker build",
        "benchmark ",
        "production wiring",
    )

    assert all(marker not in entry_point for marker in forbidden)
    assert all(marker not in opt_in_step for marker in forbidden)
