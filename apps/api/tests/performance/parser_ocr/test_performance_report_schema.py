import json

import pytest
from app.parser.performance import (
    SyntheticPerformanceBudget,
    SyntheticPerformanceSample,
    _PerformanceReportSchema,
    profile_synthetic_operation,
    serialize_performance_report,
)

REPORT_KEYS = {
    "component",
    "status",
    "latency_bucket",
    "sample_size_bucket",
    "failure_code",
}
SENSITIVE_VALUES = (
    "PRIVATE_RAW_BYTES",
    "/PRIVATE_TEMP_PATH",
    "PRIVATE_RUNTIME_REF",
    "PRIVATE_ORIGINAL_FILENAME",
    "PRIVATE_OCR_TEXT",
    "PRIVATE_EXTRACTED_TEXT",
    "PRIVATE_PARTIAL_OUTPUT",
    "PRIVATE_STDOUT",
    "PRIVATE_STDERR",
    "PRIVATE_RAW_EXCEPTION",
    "987654321",
)


def _profile(sample: SyntheticPerformanceSample) -> dict[str, str | None]:
    result = profile_synthetic_operation(
        "parser",
        SyntheticPerformanceBudget(max_elapsed_units=10, max_sample_units=8),
        lambda: sample,
    )
    return serialize_performance_report(result)


def test_normal_sample_serializes_only_allowlisted_report_schema():
    report = _profile(SyntheticPerformanceSample(5, 4, "success"))

    assert set(report) == REPORT_KEYS
    assert report == {
        "component": "parser",
        "status": "passed",
        "latency_bucket": "within_budget",
        "sample_size_bucket": "within_budget",
        "failure_code": None,
    }


@pytest.mark.parametrize(
    ("elapsed_units", "sample_units", "expected_status", "latency_bucket", "size_bucket"),
    [
        (10, 8, "passed", "within_budget", "within_budget"),
        (11, 8, "budget_exceeded", "over_budget", "within_budget"),
        (10, 9, "budget_exceeded", "within_budget", "over_budget"),
    ],
)
def test_budget_boundary_and_one_unit_over_are_deterministic_buckets(
    elapsed_units,
    sample_units,
    expected_status,
    latency_bucket,
    size_bucket,
):
    report = _profile(SyntheticPerformanceSample(elapsed_units, sample_units, "success"))

    assert report["status"] == expected_status
    assert report["latency_bucket"] == latency_bucket
    assert report["sample_size_bucket"] == size_bucket
    serialized = json.dumps(report, sort_keys=True)
    assert str(elapsed_units) not in serialized
    assert str(sample_units) not in serialized


@pytest.mark.parametrize(
    ("sample", "failure_code", "size_bucket"),
    [
        (SyntheticPerformanceSample(0, 1, "success"), None, "within_budget"),
        (SyntheticPerformanceSample(0, 0, "success"), "PERFORMANCE_EMPTY_SAMPLE", "empty"),
        (SyntheticPerformanceSample(1, 1, "timeout"), "PERFORMANCE_TIMEOUT", "unknown"),
        (SyntheticPerformanceSample(1, 1, "failed"), "PERFORMANCE_FAILED", "unknown"),
    ],
)
def test_minimum_empty_timeout_and_failure_samples_are_sanitized(sample, failure_code, size_bucket):
    report = _profile(sample)

    assert report["failure_code"] == failure_code
    assert report["sample_size_bucket"] == size_bucket
    assert set(report) == REPORT_KEYS


def test_raw_exception_is_not_present_in_failure_report_or_string():
    def fail():
        raise RuntimeError(":".join(SENSITIVE_VALUES))

    result = profile_synthetic_operation("ocr", SyntheticPerformanceBudget(10, 8), fail)
    report = serialize_performance_report(result)
    serialized = json.dumps(report, sort_keys=True)

    assert report["failure_code"] == "PERFORMANCE_FAILED"
    assert all(value not in serialized for value in SENSITIVE_VALUES)
    assert all(value not in str(report) for value in SENSITIVE_VALUES)


@pytest.mark.parametrize(
    "extra",
    [
        {"raw_file_bytes": "PRIVATE_RAW_BYTES"},
        {"temp_path": {"value": "/PRIVATE_TEMP_PATH"}},
        {"opaque_runtime_ref": ["PRIVATE_RUNTIME_REF"]},
        {"metadata": {"nested": {"ocr_text": "PRIVATE_OCR_TEXT"}}},
        {"messages": ["PRIVATE_STDOUT", "PRIVATE_STDERR"]},
    ],
)
def test_unknown_nested_and_collection_fields_are_rejected(extra):
    fields = {
        "component": "parser",
        "status": "passed",
        "latency_bucket": "within_budget",
        "sample_size_bucket": "within_budget",
        "failure_code": None,
        **extra,
    }

    with pytest.raises(ValueError, match="report fields are not allowed"):
        _PerformanceReportSchema.from_mapping(fields)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("component", {"value": "parser"}),
        ("status", ["passed"]),
        ("latency_bucket", ("within_budget",)),
        ("sample_size_bucket", {"within_budget"}),
        ("failure_code", {"code": "PERFORMANCE_FAILED"}),
    ],
)
def test_nested_or_collection_values_cannot_bypass_allowlist(key, value):
    fields = {
        "component": "parser",
        "status": "passed",
        "latency_bucket": "within_budget",
        "sample_size_bucket": "within_budget",
        "failure_code": None,
    }
    fields[key] = value

    with pytest.raises(ValueError, match="report values must be allowlisted scalar values"):
        _PerformanceReportSchema.from_mapping(fields)
