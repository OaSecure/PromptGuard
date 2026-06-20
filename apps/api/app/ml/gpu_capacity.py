from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

_MIB = 1024 * 1024


class GpuCapacityProbeError(RuntimeError):
    pass


class GpuMemorySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    free_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    device_index: int = Field(default=0, ge=0)


class GpuWorkerCapacityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    configured_workers: int = Field(ge=1)
    max_workers: int = Field(ge=1)
    reserved_memory_mb: int = Field(ge=0)
    memory_per_worker_mb: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_worker_bounds(self) -> "GpuWorkerCapacityPolicy":
        if self.configured_workers > self.max_workers:
            raise ValueError("configured worker count must not exceed max workers")
        return self


class GpuWorkerCapacityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    worker_count: int = Field(ge=1)
    reason: str


class GpuCapacityProbe(Protocol):
    def current(self) -> GpuMemorySnapshot | None: ...


class StaticGpuCapacityProbe:
    def __init__(self, snapshot: GpuMemorySnapshot | None) -> None:
        self._snapshot = snapshot

    def current(self) -> GpuMemorySnapshot | None:
        return self._snapshot


class TorchCudaGpuCapacityProbe:
    def current(self) -> GpuMemorySnapshot | None:
        try:
            import torch
        except Exception:
            return None
        cuda = getattr(torch, "cuda", None)
        if cuda is None or not cuda.is_available():
            return None
        try:
            free_bytes, total_bytes = cuda.mem_get_info()
        except Exception as exc:
            raise GpuCapacityProbeError("gpu_capacity_probe_failed") from exc
        return GpuMemorySnapshot(free_bytes=int(free_bytes), total_bytes=int(total_bytes), device_index=int(cuda.current_device()))


def resolve_gpu_worker_capacity(
    policy: GpuWorkerCapacityPolicy,
    *,
    probe: GpuCapacityProbe,
) -> GpuWorkerCapacityDecision:
    configured = _clamp(policy.configured_workers, 1, policy.max_workers)
    if not policy.enabled:
        return GpuWorkerCapacityDecision(worker_count=configured, reason="configured")
    try:
        snapshot = probe.current()
    except GpuCapacityProbeError:
        return GpuWorkerCapacityDecision(worker_count=configured, reason="gpu_probe_failed")
    if snapshot is None:
        return GpuWorkerCapacityDecision(worker_count=configured, reason="gpu_unavailable")

    reserved_bytes = policy.reserved_memory_mb * _MIB
    worker_bytes = policy.memory_per_worker_mb * _MIB
    usable_bytes = snapshot.free_bytes - reserved_bytes
    if usable_bytes < worker_bytes:
        return GpuWorkerCapacityDecision(worker_count=1, reason="gpu_capacity_below_single_worker")

    sized_workers = usable_bytes // worker_bytes
    return GpuWorkerCapacityDecision(
        worker_count=_clamp(int(sized_workers), 1, policy.max_workers),
        reason="gpu_capacity",
    )


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))
