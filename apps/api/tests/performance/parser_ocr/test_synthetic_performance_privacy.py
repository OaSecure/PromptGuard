import json
from dataclasses import asdict

from app.parser.performance import SyntheticPerformanceBudget, profile_synthetic_operation

SENSITIVE = (
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


def test_raw_exception_and_sensitive_fake_failure_are_not_exposed():
    def failing_operation():
        raise RuntimeError(":".join(SENSITIVE))

    result = profile_synthetic_operation("ocr", SyntheticPerformanceBudget(10, 8), failing_operation)
    serialized = json.dumps(asdict(result), sort_keys=True)
    assert result.failure_code == "PERFORMANCE_FAILED"
    assert all(value not in serialized for value in SENSITIVE)


def test_public_result_has_buckets_not_exact_latency_or_size():
    result_fields = set(asdict(profile_synthetic_operation("parser", SyntheticPerformanceBudget(10, 8), None)))
    assert result_fields == {"component", "status", "latency_bucket", "sample_size_bucket", "failure_code"}
    assert not {"elapsed", "elapsed_units", "size", "sample_units"} & result_fields
