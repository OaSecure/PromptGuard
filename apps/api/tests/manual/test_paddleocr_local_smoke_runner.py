import importlib.util
import json
from pathlib import Path

RUNNER_PATH = Path(__file__).with_name("run_paddleocr_local_smoke.py")
SPEC = importlib.util.spec_from_file_location("paddleocr_local_smoke", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_runner_guards_fail_closed_and_emits_only_safe_summary(monkeypatch, capsys):
    private_values = (
        runner.SYNTHETIC_TEXT,
        "PRIVATE_OCR_TEXT",
        "PRIVATE_STDOUT",
        "PRIVATE_STDERR",
        "C:\\Users\\private-user\\AppData\\Local\\Temp\\private.png",
    )
    monkeypatch.delenv(runner.OPT_IN_ENV, raising=False)

    for argv in ([], ["--local-only"], ["--synthetic-only"], ["--local-only", "--synthetic-only"]):
        assert runner.main(argv) == 2
        output = capsys.readouterr().out
        summary = json.loads(output)
        assert set(summary) == {
            "status",
            "stage_status",
            "ocr_status",
            "ocr_block_count",
            "cuda_available",
            "cleanup_success",
            "reason_code",
            "readiness",
        }
        assert summary["status"] == "blocked"
        assert summary["readiness"] is False
        assert all(value not in output for value in private_values)


def test_runner_sanitizes_runtime_failure(monkeypatch):
    monkeypatch.setenv(runner.OPT_IN_ENV, "1")

    monkeypatch.setattr(runner, "_write_synthetic_image", lambda path: (_ for _ in ()).throw(RuntimeError("PRIVATE_RAW_EXCEPTION")))

    code, summary = runner.run(local_only=True, synthetic_only=True)

    assert code == 1
    assert summary["status"] == "failed"
    assert summary["stage_status"] == "ocr"
    assert summary["ocr_block_count"] == 0
    assert summary["cleanup_success"] is True
    assert "PRIVATE_RAW_EXCEPTION" not in json.dumps(summary)
