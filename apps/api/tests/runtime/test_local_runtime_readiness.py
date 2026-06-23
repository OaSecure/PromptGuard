from pathlib import Path
from types import SimpleNamespace

from app.runtime.local_readiness import (
    DependencyProbe,
    LocalRuntimeReadinessProbe,
    LocalRuntimeReadinessReport,
    RuntimeDependencyStatus,
)

from scripts import runtime_readiness


class _UnavailableDependencyProbe:
    def check(self, dependency: str) -> RuntimeDependencyStatus:
        return RuntimeDependencyStatus(name=dependency, installed=False)


class _TorchCudaProbe:
    def __init__(self, *, installed: bool = True, cuda_available: bool = True, version: str = "2.9.1+cu128") -> None:
        self._installed = installed
        self._cuda_available = cuda_available
        self._version = version

    def check(self, dependency: str) -> RuntimeDependencyStatus:
        if dependency != "torch":
            return RuntimeDependencyStatus(name=dependency, installed=False)
        return RuntimeDependencyStatus(
            name="torch",
            installed=self._installed,
            version=self._version if self._installed else None,
            cuda_available=self._cuda_available if self._installed else None,
            device="cuda" if self._installed and self._cuda_available else None,
        )


def test_dependency_probe_reports_missing_optional_dependency_without_raw_exception_detail(monkeypatch):
    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "torch":
            raise ModuleNotFoundError("torch missing while handling PRIVATE_RAW_PROMPT")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)

    status = DependencyProbe().check("torch")

    assert status.name == "torch"
    assert status.installed is False
    assert status.reason == "dependency_unavailable"
    assert "PRIVATE_RAW_PROMPT" not in str(status.model_dump())


def test_dependency_probe_reports_torch_cuda_device_when_available(monkeypatch):
    fake_torch = SimpleNamespace(
        __version__="2.9.1+cu128",
        cuda=SimpleNamespace(is_available=lambda: True, current_device=lambda: 0),
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)

    status = DependencyProbe().check("torch")

    assert status.installed is True
    assert status.version == "2.9.1+cu128"
    assert status.cuda_available is True
    assert status.device == "cuda:0"


def test_runtime_readiness_requires_torch_cuda_for_cuda_expected_runtime():
    report = LocalRuntimeReadinessProbe(
        dependency_probe=_TorchCudaProbe(installed=True, cuda_available=False, version="2.9.1+cpu"),
        expected_cuda=True,
    ).check()

    assert report.ready is False
    assert report.runtime == "python"
    assert report.blockers == ["torch_cuda_unavailable"]
    assert report.dependencies["torch"].installed is True
    assert report.dependencies["torch"].cuda_available is False


def test_runtime_readiness_passes_when_torch_cuda_is_available():
    report = LocalRuntimeReadinessProbe(
        dependency_probe=_TorchCudaProbe(installed=True, cuda_available=True),
        expected_cuda=True,
    ).check()

    assert report.ready is True
    assert report.blockers == []
    assert report.dependencies["torch"].device == "cuda"


def test_runtime_readiness_has_no_sensitive_payload_fields():
    report = LocalRuntimeReadinessProbe(
        dependency_probe=_UnavailableDependencyProbe(),
        expected_cuda=True,
    ).check()

    encoded = str(report.model_dump()).lower()
    assert "raw_prompt" not in encoded
    assert "file_content" not in encoded
    assert "extracted_text" not in encoded
    assert "embedding_vector" not in encoded
    assert "original_filename" not in encoded


def test_runtime_readiness_script_emits_metadata_only_json(monkeypatch, capsys):
    class FakeProbe:
        def __init__(self, *, expected_cuda: bool) -> None:
            assert expected_cuda is True

        def check(self) -> LocalRuntimeReadinessReport:
            return LocalRuntimeReadinessReport(
                runtime="python",
                python_version="3.11.0",
                platform="windows",
                ready=True,
                blockers=[],
                dependencies={"torch": RuntimeDependencyStatus(name="torch", installed=True, cuda_available=True, device="cuda:0")},
            )

    monkeypatch.setattr(runtime_readiness, "LocalRuntimeReadinessProbe", FakeProbe)

    exit_code = runtime_readiness.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"ready": true' in output
    assert "raw_prompt" not in output
    assert "file_content" not in output
    assert "original_filename" not in output


def test_cuda_requirements_pin_pytorch_cuda_index():
    requirements = Path(__file__).parents[2] / "requirements-ml-cu128.txt"
    content = requirements.read_text(encoding="utf-8")

    assert "--index-url https://download.pytorch.org/whl/cu128" in content
    assert "torch==2.9.1" in content
    assert "cpu" not in content.casefold()
