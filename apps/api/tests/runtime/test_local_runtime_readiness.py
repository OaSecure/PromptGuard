import json
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
    def __init__(self, *, installed: bool = True, cuda_available: bool = True, version: str = "2.9.1+cu126") -> None:
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
        __version__="2.9.1+cu126",
        cuda=SimpleNamespace(is_available=lambda: True, current_device=lambda: 0),
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)

    status = DependencyProbe().check("torch")

    assert status.installed is True
    assert status.version == "2.9.1+cu126"
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


def test_runtime_readiness_can_require_ocr_dependencies():
    class OcrProbe:
        def check(self, dependency: str) -> RuntimeDependencyStatus:
            if dependency == "torch":
                return RuntimeDependencyStatus(
                    name="torch",
                    installed=True,
                    version="2.9.1+cu126",
                    cuda_available=True,
                    device="cuda:0",
                )
            if dependency == "tesseract-kor":
                return RuntimeDependencyStatus(name=dependency, installed=False, reason="tesseract_korean_unavailable")
            if dependency == "paddleocr":
                return RuntimeDependencyStatus(name=dependency, installed=False, reason="dependency_unavailable")
            return RuntimeDependencyStatus(name=dependency, installed=False, reason="unsupported_dependency_probe")

    report = LocalRuntimeReadinessProbe(
        dependency_probe=OcrProbe(),
        expected_cuda=True,
        include_ocr=True,
    ).check()

    assert report.ready is False
    assert report.blockers == ["tesseract_kor_unavailable", "paddleocr_unavailable"]
    assert set(report.dependencies) == {"torch", "tesseract-kor", "paddleocr"}
    assert report.dependencies["tesseract-kor"].reason == "tesseract_korean_unavailable"


def test_runtime_readiness_can_check_ocr_worker_without_torch_dependency():
    class OcrOnlyProbe:
        def check(self, dependency: str) -> RuntimeDependencyStatus:
            if dependency == "tesseract-kor":
                return RuntimeDependencyStatus(name=dependency, installed=True)
            if dependency == "paddleocr":
                return RuntimeDependencyStatus(name=dependency, installed=True, cuda_available=True, device="gpu")
            return RuntimeDependencyStatus(name=dependency, installed=False, reason="unexpected_dependency_probe")

    report = LocalRuntimeReadinessProbe(
        dependency_probe=OcrOnlyProbe(),
        expected_cuda=True,
        include_torch=False,
        include_ocr=True,
    ).check()

    assert report.ready is True
    assert report.blockers == []
    assert set(report.dependencies) == {"tesseract-kor", "paddleocr"}


def test_runtime_readiness_has_no_sensitive_payload_fields():
    report = LocalRuntimeReadinessProbe(
        dependency_probe=_UnavailableDependencyProbe(),
        expected_cuda=True,
        include_ocr=True,
    ).check()

    encoded = str(report.model_dump()).lower()
    assert "raw_prompt" not in encoded
    assert "file_content" not in encoded
    assert "extracted_text" not in encoded
    assert "embedding_vector" not in encoded
    assert "original_filename" not in encoded


def test_runtime_readiness_script_emits_metadata_only_json(monkeypatch, capfd):
    class FakeProbe:
        def __init__(self, *, expected_cuda: bool, include_torch: bool, include_ocr: bool) -> None:
            assert expected_cuda is True
            assert include_torch is True
            assert include_ocr is False

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

    exit_code = runtime_readiness.main([])
    output = capfd.readouterr().out

    assert exit_code == 0
    assert '"ready": true' in output
    assert "raw_prompt" not in output
    assert "file_content" not in output
    assert "original_filename" not in output


def test_runtime_readiness_script_can_include_ocr_checks(monkeypatch, capfd):
    class FakeProbe:
        def __init__(self, *, expected_cuda: bool, include_torch: bool, include_ocr: bool) -> None:
            assert expected_cuda is True
            assert include_torch is True
            assert include_ocr is True

        def check(self) -> LocalRuntimeReadinessReport:
            return LocalRuntimeReadinessReport(
                runtime="python",
                python_version="3.11.0",
                platform="windows",
                ready=False,
                blockers=["paddleocr_unavailable"],
                dependencies={
                    "torch": RuntimeDependencyStatus(name="torch", installed=True, cuda_available=True, device="cuda:0"),
                    "paddleocr": RuntimeDependencyStatus(name="paddleocr", installed=False, reason="dependency_unavailable"),
                },
            )

    monkeypatch.setattr(runtime_readiness, "LocalRuntimeReadinessProbe", FakeProbe)
    exit_code = runtime_readiness.main(["--include-ocr"])
    output = capfd.readouterr().out

    assert exit_code == 1
    assert "paddleocr_unavailable" in output
    assert "raw_prompt" not in output


def test_runtime_readiness_script_can_check_ocr_worker_target_without_torch(monkeypatch, capfd):
    class FakeProbe:
        def __init__(self, *, expected_cuda: bool, include_torch: bool, include_ocr: bool) -> None:
            assert expected_cuda is True
            assert include_torch is False
            assert include_ocr is True

        def check(self) -> LocalRuntimeReadinessReport:
            return LocalRuntimeReadinessReport(
                runtime="python",
                python_version="3.11.0",
                platform="windows",
                ready=True,
                blockers=[],
                dependencies={
                    "paddleocr": RuntimeDependencyStatus(name="paddleocr", installed=True, cuda_available=True, device="gpu"),
                },
            )

    monkeypatch.setattr(runtime_readiness, "LocalRuntimeReadinessProbe", FakeProbe)
    exit_code = runtime_readiness.main(["--target", "ocr"])
    output = capfd.readouterr().out

    assert exit_code == 0
    assert '"ready": true' in output
    assert "torch" not in output


def test_runtime_package_init_keeps_worker_dependencies_lazy():
    runtime_init = Path(__file__).parents[2] / "app" / "runtime" / "__init__.py"
    content = runtime_init.read_text(encoding="utf-8")

    assert "parser_worker" not in content
    assert "ml_inference_queue" not in content


def test_runtime_readiness_script_keeps_probe_noise_out_of_stdout(monkeypatch, capfd):
    class NoisyProbe:
        def __init__(self, *, expected_cuda: bool, include_torch: bool, include_ocr: bool) -> None:
            assert expected_cuda is True
            assert include_torch is True
            assert include_ocr is True

        def check(self) -> LocalRuntimeReadinessReport:
            print("PADDLE_IMPORT_WARNING PRIVATE_RAW_PROMPT")
            print("TESSERACT_PATH_WARNING ORIGINAL_FILENAME", file=__import__("sys").stderr)
            return LocalRuntimeReadinessReport(
                runtime="python",
                python_version="3.11.0",
                platform="windows",
                ready=False,
                blockers=["tesseract_kor_unavailable"],
                dependencies={
                    "torch": RuntimeDependencyStatus(name="torch", installed=True, cuda_available=True, device="cuda:0"),
                    "paddleocr": RuntimeDependencyStatus(name="paddleocr", installed=True, cuda_available=True, device="gpu"),
                    "tesseract-kor": RuntimeDependencyStatus(
                        name="tesseract-kor",
                        installed=False,
                        reason="tesseract_binary_unavailable",
                    ),
                },
            )

    monkeypatch.setattr(runtime_readiness, "LocalRuntimeReadinessProbe", NoisyProbe)
    exit_code = runtime_readiness.main(["--include-ocr"])
    captured = capfd.readouterr()

    assert exit_code == 1
    payload = json.loads(captured.out)
    assert payload["blockers"] == ["tesseract_kor_unavailable"]
    assert captured.out.count("\n") == 1
    assert "PADDLE_IMPORT_WARNING" not in captured.out
    assert "PRIVATE_RAW_PROMPT" not in captured.out


def test_cuda_requirements_pin_pytorch_cuda_index():
    api_requirements = (Path(__file__).parents[2] / "requirements.txt").read_text(encoding="utf-8")
    requirements = Path(__file__).parents[2] / "requirements-torch-gpu.txt"
    content = requirements.read_text(encoding="utf-8")

    assert "torch==" not in api_requirements
    assert "--extra-index-url https://download.pytorch.org/whl/cu126" in content
    assert "pydantic==2.13.4" in content
    assert "torch==2.9.1+cu126" in content
    assert "sentence-transformers==5.4.1" in content
    assert "transformers==4.57.1" in content
    assert "cpu" not in content.casefold()


def test_ocr_gpu_requirements_pin_paddle_cuda_runtime():
    api_requirements = (Path(__file__).parents[2] / "requirements.txt").read_text(encoding="utf-8")
    requirements = Path(__file__).parents[2] / "requirements-paddle-gpu.txt"
    content = requirements.read_text(encoding="utf-8")

    assert "paddleocr==" not in api_requirements
    assert "paddlepaddle-gpu==" not in api_requirements
    assert "--extra-index-url https://www.paddlepaddle.org.cn/packages/stable/cu126/" in content
    assert "paddlepaddle-gpu==3.3.1" in content
    assert "numpy==2.3.5" in content
    assert "paddleocr==3.7.0" in content
    assert "pypdfium2==5.10.1" in content
    assert "cu118" not in content
    assert "paddlepaddle==" not in content

