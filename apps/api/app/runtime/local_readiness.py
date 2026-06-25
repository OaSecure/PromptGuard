import os
import platform
import shutil
import subprocess
import sys
from importlib import import_module
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
        if dependency == "torch":
            return self._check_torch()
        if dependency == "tesseract-kor":
            return self._check_tesseract_korean()
        if dependency == "paddleocr":
            return self._check_paddleocr()
        return RuntimeDependencyStatus(name=dependency, installed=False, reason="unsupported_dependency_probe")

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

    def _check_tesseract_korean(self) -> RuntimeDependencyStatus:
        binary = os.environ.get("PROMPTGUARD_TESSERACT_BINARY_PATH") or shutil.which("tesseract")
        if not binary:
            return RuntimeDependencyStatus(
                name="tesseract-kor",
                installed=False,
                reason="tesseract_binary_unavailable",
            )
        try:
            completed = subprocess.run(
                [binary, "--list-langs"],
                check=False,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except Exception:
            return RuntimeDependencyStatus(
                name="tesseract-kor",
                installed=False,
                reason="tesseract_language_probe_failed",
            )
        if completed.returncode != 0:
            return RuntimeDependencyStatus(
                name="tesseract-kor",
                installed=False,
                reason="tesseract_language_probe_failed",
            )
        languages = {
            line.strip()
            for line in completed.stdout.splitlines()
            if line.strip() and not line.startswith("List of available languages")
        }
        if "kor" not in languages:
            return RuntimeDependencyStatus(
                name="tesseract-kor",
                installed=False,
                reason="tesseract_korean_unavailable",
            )
        return RuntimeDependencyStatus(name="tesseract-kor", installed=True)

    def _check_paddleocr(self) -> RuntimeDependencyStatus:
        try:
            paddle = import_module("paddle")
            paddleocr = import_module("paddleocr")
        except Exception:
            return RuntimeDependencyStatus(name="paddleocr", installed=False, reason="dependency_unavailable")

        cuda_available = None
        try:
            cuda_available = bool(paddle.device.is_compiled_with_cuda())
        except Exception:
            cuda_available = False
        return RuntimeDependencyStatus(
            name="paddleocr",
            installed=True,
            version=str(getattr(paddleocr, "__version__", "")) or None,
            cuda_available=cuda_available,
            device="gpu" if cuda_available else None,
        )


class LocalRuntimeReadinessProbe:
    def __init__(
        self,
        *,
        dependency_probe: RuntimeDependencyProbe | None = None,
        expected_cuda: bool = True,
        include_torch: bool = True,
        include_ocr: bool = False,
    ) -> None:
        self._dependency_probe = dependency_probe or DependencyProbe()
        self._expected_cuda = expected_cuda
        self._include_torch = include_torch
        self._include_ocr = include_ocr

    def check(self) -> LocalRuntimeReadinessReport:
        dependencies = {}
        if self._include_torch:
            dependencies["torch"] = self._dependency_probe.check("torch")
        if self._include_ocr:
            dependencies["tesseract-kor"] = self._dependency_probe.check("tesseract-kor")
            dependencies["paddleocr"] = self._dependency_probe.check("paddleocr")
        blockers = _runtime_blockers(
            dependencies,
            expected_cuda=self._expected_cuda,
            include_torch=self._include_torch,
            include_ocr=self._include_ocr,
        )

        return LocalRuntimeReadinessReport(
            runtime="python",
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            platform=platform.system().lower() or "unknown",
            ready=not blockers,
            blockers=blockers,
            dependencies=dependencies,
        )


def _runtime_blockers(
    dependencies: dict[str, RuntimeDependencyStatus],
    *,
    expected_cuda: bool,
    include_torch: bool,
    include_ocr: bool,
) -> list[str]:
    blockers: list[str] = []
    if include_torch:
        torch_status = dependencies["torch"]
        if not torch_status.installed:
            blockers.append("torch_unavailable")
        elif expected_cuda and torch_status.cuda_available is not True:
            blockers.append("torch_cuda_unavailable")
    if include_ocr:
        blockers.extend(_ocr_blockers(dependencies, expected_cuda=expected_cuda))
    return blockers


def _ocr_blockers(
    dependencies: dict[str, RuntimeDependencyStatus],
    *,
    expected_cuda: bool,
) -> list[str]:
    blockers: list[str] = []
    if not dependencies["tesseract-kor"].installed:
        blockers.append("tesseract_kor_unavailable")
    paddle_status = dependencies["paddleocr"]
    if not paddle_status.installed:
        blockers.append("paddleocr_unavailable")
    elif expected_cuda and paddle_status.cuda_available is not True:
        blockers.append("paddleocr_cuda_unavailable")
    return blockers
