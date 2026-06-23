import platform
import sys
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class RuntimeDependencyStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    installed: bool
    version: str | None = None
    cuda_available: bool | None = None
    device: str | None = None
    reason: str | None = None


class LocalRuntimeReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime: str
    python_version: str
    platform: str
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    dependencies: dict[str, RuntimeDependencyStatus] = Field(default_factory=dict)


class RuntimeDependencyProbe(Protocol):
    def check(self, dependency: str) -> RuntimeDependencyStatus: ...


class DependencyProbe:
    def check(self, dependency: str) -> RuntimeDependencyStatus:
        if dependency != "torch":
            return RuntimeDependencyStatus(name=dependency, installed=False, reason="unsupported_dependency_probe")
        return self._check_torch()

    def _check_torch(self) -> RuntimeDependencyStatus:
        try:
            import torch
        except Exception:
            return RuntimeDependencyStatus(name="torch", installed=False, reason="dependency_unavailable")

        cuda = getattr(torch, "cuda", None)
        if cuda is None:
            return RuntimeDependencyStatus(
                name="torch",
                installed=True,
                version=str(getattr(torch, "__version__", "")) or None,
                cuda_available=False,
            )
        cuda_available = bool(cuda.is_available())
        device = None
        if cuda_available:
            try:
                device = f"cuda:{int(cuda.current_device())}"
            except Exception:
                device = "cuda"
        return RuntimeDependencyStatus(
            name="torch",
            installed=True,
            version=str(getattr(torch, "__version__", "")) or None,
            cuda_available=cuda_available,
            device=device,
        )


class LocalRuntimeReadinessProbe:
    def __init__(
        self,
        *,
        dependency_probe: RuntimeDependencyProbe | None = None,
        expected_cuda: bool = True,
    ) -> None:
        self._dependency_probe = dependency_probe or DependencyProbe()
        self._expected_cuda = expected_cuda

    def check(self) -> LocalRuntimeReadinessReport:
        dependencies = {"torch": self._dependency_probe.check("torch")}
        blockers: list[str] = []
        torch_status = dependencies["torch"]
        if not torch_status.installed:
            blockers.append("torch_unavailable")
        elif self._expected_cuda and torch_status.cuda_available is not True:
            blockers.append("torch_cuda_unavailable")

        return LocalRuntimeReadinessReport(
            runtime="python",
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            platform=platform.system().lower() or "unknown",
            ready=not blockers,
            blockers=blockers,
            dependencies=dependencies,
        )
