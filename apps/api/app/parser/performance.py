"""Deterministic, privacy-safe performance contract for synthetic parser/OCR samples."""

from dataclasses import dataclass
from typing import Callable, Literal

PerformanceComponent = Literal["parser", "ocr"]
SampleOutcome = Literal["success", "timeout", "failed", "partial"]
ProfileStatus = Literal["passed", "budget_exceeded", "failed"]
LatencyBucket = Literal["within_budget", "over_budget", "unknown"]
SampleSizeBucket = Literal["within_budget", "over_budget", "empty", "unknown"]


@dataclass(frozen=True)
class SyntheticPerformanceBudget:
    max_elapsed_units: int
    max_sample_units: int

    def __post_init__(self) -> None:
        if self.max_elapsed_units <= 0 or self.max_sample_units <= 0:
            raise ValueError("performance budgets must be positive")


@dataclass(frozen=True)
class SyntheticPerformanceSample:
    elapsed_units: int
    sample_units: int
    outcome: SampleOutcome


@dataclass(frozen=True)
class SyntheticPerformanceResult:
    component: PerformanceComponent
    status: ProfileStatus
    latency_bucket: LatencyBucket
    sample_size_bucket: SampleSizeBucket
    failure_code: str | None = None


def profile_synthetic_operation(
    component: PerformanceComponent,
    budget: SyntheticPerformanceBudget,
    operation: Callable[[], object] | None,
) -> SyntheticPerformanceResult:
    if operation is None:
        return _failure(component, "PERFORMANCE_DEPENDENCY_UNAVAILABLE")
    try:
        sample = operation()
    except Exception:
        return _failure(component, "PERFORMANCE_FAILED")
    if not isinstance(sample, SyntheticPerformanceSample):
        return _failure(component, "PERFORMANCE_MALFORMED_SAMPLE")
    sample_failure = _sample_failure(sample)
    if sample_failure is not None:
        code, size_bucket = sample_failure
        return _failure(component, code, size_bucket=size_bucket)
    return _budget_result(component, budget, sample)


def _sample_failure(
    sample: SyntheticPerformanceSample,
) -> tuple[str, Literal["empty", "unknown"]] | None:
    if sample.elapsed_units < 0 or sample.sample_units < 0:
        return "PERFORMANCE_MALFORMED_SAMPLE", "unknown"
    if sample.sample_units == 0:
        return "PERFORMANCE_EMPTY_SAMPLE", "empty"
    code = {
        "timeout": "PERFORMANCE_TIMEOUT",
        "failed": "PERFORMANCE_FAILED",
        "partial": "PERFORMANCE_PARTIAL",
    }.get(sample.outcome)
    return (code, "unknown") if code is not None else None


def _budget_result(
    component: PerformanceComponent,
    budget: SyntheticPerformanceBudget,
    sample: SyntheticPerformanceSample,
) -> SyntheticPerformanceResult:
    latency_bucket: LatencyBucket = (
        "within_budget" if sample.elapsed_units <= budget.max_elapsed_units else "over_budget"
    )
    size_bucket: SampleSizeBucket = "within_budget" if sample.sample_units <= budget.max_sample_units else "over_budget"
    status: ProfileStatus = "passed" if latency_bucket == size_bucket == "within_budget" else "budget_exceeded"
    return SyntheticPerformanceResult(component, status, latency_bucket, size_bucket)


def _failure(
    component: PerformanceComponent,
    code: str,
    *,
    size_bucket: Literal["empty", "unknown"] = "unknown",
) -> SyntheticPerformanceResult:
    return SyntheticPerformanceResult(component, "failed", "unknown", size_bucket, code)
