import pytest
from app.parser.performance import (
    SyntheticPerformanceBudget,
    SyntheticPerformanceSample,
    profile_synthetic_operation,
)


class FakeOperation:
    def __init__(self, sample=None, error=None):
        self.sample = sample
        self.error = error
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.sample


@pytest.mark.parametrize("component", ["parser", "ocr"])
def test_synthetic_parser_and_fake_ocr_profiles_pass_without_real_runtime(component):
    operation = FakeOperation(SyntheticPerformanceSample(elapsed_units=5, sample_units=4, outcome="success"))
    result = profile_synthetic_operation(component, SyntheticPerformanceBudget(10, 8), operation)
    assert operation.calls == 1
    assert result.status == "passed"
    assert result.latency_bucket == "within_budget"
    assert result.sample_size_bucket == "within_budget"


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [(10, "passed"), (11, "budget_exceeded")],
)
def test_elapsed_budget_boundary_and_one_unit_over(elapsed, expected):
    operation = FakeOperation(SyntheticPerformanceSample(elapsed, 1, "success"))
    result = profile_synthetic_operation("parser", SyntheticPerformanceBudget(10, 8), operation)
    assert result.status == expected


@pytest.mark.parametrize(
    ("sample", "failure_code"),
    [
        (SyntheticPerformanceSample(1, 0, "success"), "PERFORMANCE_EMPTY_SAMPLE"),
        (SyntheticPerformanceSample(1, 1, "timeout"), "PERFORMANCE_TIMEOUT"),
        (SyntheticPerformanceSample(1, 1, "failed"), "PERFORMANCE_FAILED"),
        (SyntheticPerformanceSample(1, 1, "partial"), "PERFORMANCE_PARTIAL"),
    ],
)
def test_empty_timeout_failure_and_partial_samples_fail_closed(sample, failure_code):
    result = profile_synthetic_operation("ocr", SyntheticPerformanceBudget(10, 8), FakeOperation(sample))
    assert result.status == "failed"
    assert result.failure_code == failure_code


def test_missing_dependency_and_malformed_sample_fail_safe():
    missing = profile_synthetic_operation("parser", SyntheticPerformanceBudget(10, 8), None)
    malformed = profile_synthetic_operation("parser", SyntheticPerformanceBudget(10, 8), FakeOperation(object()))
    assert missing.failure_code == "PERFORMANCE_DEPENDENCY_UNAVAILABLE"
    assert malformed.failure_code == "PERFORMANCE_MALFORMED_SAMPLE"
