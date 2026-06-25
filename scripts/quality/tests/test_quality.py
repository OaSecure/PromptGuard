import ast
from collections import Counter
from pathlib import Path

import pytest

from scripts.quality.quality import (
    QualityFailure,
    architecture_violations,
    compare_baseline,
    fingerprint,
    normalize_path,
    privacy_violations,
    unicode_violations,
    validate_baseline_change,
)


def test_baseline_match_and_new_stale_or_count_changes():
    baseline = Counter({"a": 1, "b": 2})
    compare_baseline(baseline, baseline, "fake")
    for current in (Counter({"a": 2, "b": 2}), Counter({"a": 1}), Counter({"a": 1, "b": 2, "c": 1})):
        with pytest.raises(QualityFailure):
            compare_baseline(current, baseline, "fake")


def test_fingerprint_ignores_platform_path_and_line_number():
    windows = fingerprint("mypy", r"C:\repo\apps\api\app\x.py", "attr-defined", "error at line 10")
    posix = fingerprint("mypy", "/repo/apps/api/app/x.py", "attr-defined", "error at line 99")
    assert windows.split("|", 2)[1:] == posix.split("|", 2)[1:]
    assert normalize_path(r"apps\api\app\x.py") == "apps/api/app/x.py"


def test_bootstrap_is_allowed_but_later_baseline_increase_is_rejected():
    validate_baseline_change(None, Counter({"bootstrap": 10}), "fake.json")
    validate_baseline_change(Counter({"old": 2}), Counter({"old": 1}), "fake.json")
    with pytest.raises(QualityFailure):
        validate_baseline_change(Counter({"old": 1}), Counter({"old": 2}), "fake.json")
    with pytest.raises(QualityFailure):
        validate_baseline_change(Counter({"old": 1}), Counter({"old": 1, "new": 1}), "fake.json")


def test_radon_hotspot_complexity_change_is_new_and_stale():
    old = Counter({"radon|file.py|function|f||complexity=11": 1})
    increased = Counter({"radon|file.py|function|f||complexity=12": 1})
    with pytest.raises(QualityFailure):
        compare_baseline(increased, old, "radon")


@pytest.mark.parametrize("escaped", ["\\u202e", "\\u200b", "\\x01", "A\\ufeffB"])
def test_unicode_controls_are_materialized_only_in_tmp_path(tmp_path, escaped):
    value = escaped.encode().decode("unicode_escape")
    path = tmp_path / "bad.py"
    path.write_text(value, encoding="utf-8")
    assert unicode_violations([path])


def test_plain_unicode_source_passes(tmp_path):
    path = tmp_path / "ok.py"
    path.write_text("value = '한글 🙂'\n", encoding="utf-8")
    assert unicode_violations([path]) == []


def test_architecture_forbidden_and_allowed_imports(tmp_path):
    domain = tmp_path / "apps/api/app/domain"
    domain.mkdir(parents=True)
    (domain / "bad.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")
    assert architecture_violations(tmp_path)
    (domain / "bad.py").write_text("from dataclasses import dataclass\n", encoding="utf-8")
    assert architecture_violations(tmp_path) == []


def test_privacy_scanner_is_context_aware(tmp_path):
    runtime = tmp_path / "apps/api/app/interfaces/http/analyze_request.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("file_ref: str\nsize_bytes: int\n", encoding="utf-8")
    serializer = tmp_path / "apps/api/app/privacy/event_serializer.py"
    serializer.parent.mkdir(parents=True)
    serializer.write_text("class Event:\n    masked_prompt: str\n", encoding="utf-8")
    assert privacy_violations(tmp_path) == ["apps/api/app/privacy/event_serializer.py|forbidden-field|masked_prompt"]


def test_unrestricted_persistence_model_dump_is_detected(tmp_path):
    serializer = tmp_path / "apps/api/app/privacy/event_serializer.py"
    serializer.parent.mkdir(parents=True)
    serializer.write_text("def persist(value):\n    return value.model_dump()\n", encoding="utf-8")
    assert "unrestricted-model-dump" in " ".join(privacy_violations(tmp_path))


def test_quality_tests_do_not_contain_literal_bidi_controls():
    source = Path(__file__).read_text(encoding="utf-8")
    ast.parse(source)
    assert unicode_violations([Path(__file__)]) == []
