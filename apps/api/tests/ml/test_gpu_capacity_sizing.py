from app.ml.gpu_capacity import (
    GpuCapacityProbeError,
    GpuMemorySnapshot,
    GpuWorkerCapacityPolicy,
    StaticGpuCapacityProbe,
    TorchCudaGpuCapacityProbe,
    resolve_gpu_worker_capacity,
)
from app.core.config import Settings
from app.routes import analyze as analyze_route


class _FailingProbe:
    def current(self):
        raise GpuCapacityProbeError("raw probe detail must not leak")


def test_gpu_worker_capacity_disabled_uses_configured_workers():
    decision = resolve_gpu_worker_capacity(
        GpuWorkerCapacityPolicy(
            enabled=False,
            configured_workers=3,
            max_workers=8,
            reserved_memory_mb=1024,
            memory_per_worker_mb=2048,
        ),
        probe=StaticGpuCapacityProbe(GpuMemorySnapshot(free_bytes=10 * 1024**3, total_bytes=12 * 1024**3)),
    )

    assert decision.worker_count == 3
    assert decision.reason == "configured"


def test_gpu_worker_capacity_no_gpu_falls_back_to_configured_workers():
    decision = resolve_gpu_worker_capacity(
        GpuWorkerCapacityPolicy(
            enabled=True,
            configured_workers=2,
            max_workers=8,
            reserved_memory_mb=1024,
            memory_per_worker_mb=2048,
        ),
        probe=StaticGpuCapacityProbe(None),
    )

    assert decision.worker_count == 2
    assert decision.reason == "gpu_unavailable"


def test_gpu_worker_capacity_probe_error_is_sanitized_and_falls_back():
    decision = resolve_gpu_worker_capacity(
        GpuWorkerCapacityPolicy(
            enabled=True,
            configured_workers=2,
            max_workers=8,
            reserved_memory_mb=1024,
            memory_per_worker_mb=2048,
        ),
        probe=_FailingProbe(),
    )

    assert decision.worker_count == 2
    assert decision.reason == "gpu_probe_failed"
    assert "raw probe detail" not in str(decision.model_dump())


def test_gpu_worker_capacity_exact_boundary_uses_remaining_memory():
    mib = 1024 * 1024
    decision = resolve_gpu_worker_capacity(
        GpuWorkerCapacityPolicy(
            enabled=True,
            configured_workers=1,
            max_workers=8,
            reserved_memory_mb=1024,
            memory_per_worker_mb=2048,
        ),
        probe=StaticGpuCapacityProbe(GpuMemorySnapshot(free_bytes=(1024 + 2048 * 3) * mib, total_bytes=12_000 * mib)),
    )

    assert decision.worker_count == 3
    assert decision.reason == "gpu_capacity"


def test_gpu_worker_capacity_clamps_to_max_workers():
    mib = 1024 * 1024
    decision = resolve_gpu_worker_capacity(
        GpuWorkerCapacityPolicy(
            enabled=True,
            configured_workers=1,
            max_workers=4,
            reserved_memory_mb=1024,
            memory_per_worker_mb=1024,
        ),
        probe=StaticGpuCapacityProbe(GpuMemorySnapshot(free_bytes=20_000 * mib, total_bytes=24_000 * mib)),
    )

    assert decision.worker_count == 4
    assert decision.reason == "gpu_capacity"


def test_gpu_worker_capacity_low_memory_uses_single_worker_boundary():
    mib = 1024 * 1024
    decision = resolve_gpu_worker_capacity(
        GpuWorkerCapacityPolicy(
            enabled=True,
            configured_workers=4,
            max_workers=8,
            reserved_memory_mb=1024,
            memory_per_worker_mb=2048,
        ),
        probe=StaticGpuCapacityProbe(GpuMemorySnapshot(free_bytes=1500 * mib, total_bytes=12_000 * mib)),
    )

    assert decision.worker_count == 1
    assert decision.reason == "gpu_capacity_below_single_worker"


def test_gpu_worker_capacity_policy_rejects_invalid_boundaries():
    try:
        GpuWorkerCapacityPolicy(
            enabled=True,
            configured_workers=0,
            max_workers=8,
            reserved_memory_mb=1024,
            memory_per_worker_mb=2048,
        )
    except ValueError as exc:
        assert "worker" in str(exc)
    else:
        raise AssertionError("invalid configured_workers should fail")


def test_torch_cuda_probe_returns_none_when_torch_is_unavailable(monkeypatch):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ModuleNotFoundError("torch")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    assert TorchCudaGpuCapacityProbe().current() is None


def test_analyze_route_resolves_queue_workers_from_gpu_capacity(monkeypatch):
    mib = 1024 * 1024
    monkeypatch.setattr(
        analyze_route,
        "TorchCudaGpuCapacityProbe",
        lambda: StaticGpuCapacityProbe(GpuMemorySnapshot(free_bytes=(1024 + 2048 * 3) * mib, total_bytes=12_000 * mib)),
    )
    settings = Settings(
        PROMPTGUARD_ML_INFERENCE_QUEUE_MAX_WORKERS=4,
        PROMPTGUARD_ML_INFERENCE_GPU_CAPACITY_ENABLED=True,
        PROMPTGUARD_ML_INFERENCE_GPU_RESERVED_MEMORY_MB=1024,
        PROMPTGUARD_ML_INFERENCE_GPU_MEMORY_PER_WORKER_MB=2048,
    )

    assert analyze_route._resolve_ml_inference_max_workers(settings) == 3
