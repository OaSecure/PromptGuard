import importlib.util
import json
from pathlib import Path

RUNNER_PATH = Path(__file__).with_name("run_tesseract_local_smoke.py")
SPEC = importlib.util.spec_from_file_location("tesseract_local_smoke", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_runner_guards_fail_closed_and_emits_only_safe_summary(monkeypatch, capsys):
    private_values = (
        "PRIVATE_OCR_TEXT",
        "PRIVATE_STDOUT",
        "PRIVATE_STDERR",
        "PRIVATE_ARGV",
        "PRIVATE_RAW_EXCEPTION",
        "C:\\Users\\private-user\\AppData\\Local\\Temp\\private.png",
    )
    monkeypatch.delenv(runner.OPT_IN_ENV, raising=False)
    monkeypatch.setenv(runner.BINARY_ENV, private_values[-1])

    for argv in ([], ["--local-only"], ["--synthetic-only"], ["--local-only", "--synthetic-only"]):
        assert runner.main(argv) == 2
        output = capsys.readouterr().out
        summary = json.loads(output)
        assert set(summary) == {
            "status",
            "stage_status",
            "ocr_block_count",
            "cleanup_success",
            "reason_code",
            "readiness",
        }
        assert summary["status"] == "blocked"
        assert summary["readiness"] is False
        assert all(value not in output for value in private_values)

    monkeypatch.setenv(runner.OPT_IN_ENV, "1")
    selection_calls = 0

    def forbidden_selection(*args, **kwargs):
        nonlocal selection_calls
        selection_calls += 1
        raise AssertionError("preflight failure must stop before engine selection")

    monkeypatch.setattr(runner, "select_parser_ocr_engine", forbidden_selection)
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(RuntimeError(private_values[3])))
    code, summary = runner.run(local_only=True, synthetic_only=True)
    assert code == 1
    assert selection_calls == 0
    assert summary["stage_status"] == "preflight"
    assert summary["readiness"] is False
    assert all(value not in json.dumps(summary) for value in private_values)


def test_runner_reports_readiness_when_local_ocr_succeeds(monkeypatch, tmp_path):
    binary = tmp_path / "tesseract.exe"
    tessdata = tmp_path / "tessdata"
    traineddata = tessdata / "kor.traineddata"
    binary.write_bytes(b"binary")
    tessdata.mkdir()
    traineddata.write_bytes(b"traineddata")
    monkeypatch.setenv(runner.OPT_IN_ENV, "1")
    monkeypatch.setenv(runner.BINARY_ENV, str(binary))
    monkeypatch.setenv(runner.TESSDATA_ENV, str(tessdata))
    monkeypatch.setenv(runner.LANG_ENV, "kor")
    monkeypatch.setattr(runner.hashlib, "sha256", lambda content: type("Hash", (), {"hexdigest": lambda self: "hash"})())

    class SuccessfulEngine:
        def integrate(self, native, runtime_ref, coverage, options):
            block = type("Block", (), {"source_type": "pdf_ocr_page"})()
            document = type("Document", (), {"blocks": [block]})()
            return type("Result", (), {"failure": None, "document": document})()

    monkeypatch.setattr(runner, "select_parser_ocr_engine", lambda *args, **kwargs: object())
    monkeypatch.setattr(runner, "PdfSelectedPageOcrIntegrator", lambda renderer, engine: SuccessfulEngine())

    code, summary = runner.run(local_only=True, synthetic_only=True)

    assert code == 0
    assert summary == {
        "status": "success",
        "stage_status": "ocr",
        "ocr_block_count": 1,
        "cleanup_success": True,
        "reason_code": runner.SAFE_REASON,
        "readiness": True,
    }
