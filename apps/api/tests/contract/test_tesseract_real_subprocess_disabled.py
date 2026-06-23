import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[4]
API = ROOT / "apps" / "api"
APP = API / "app"
OCR_INFRA = APP / "infrastructure" / "ocr"
REPORT = ROOT / "third_party" / "licenses" / "tesseract_ocr_candidate_report.json"

FORBIDDEN_PROCESS_CALLS = {
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("os", "system"),
    ("os", "popen"),
}


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _qualified_call(node: ast.Call) -> tuple[str, str] | None:
    function = node.func
    if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
        return function.value.id, function.attr
    return None


def test_only_isolated_backend_imports_subprocess_and_no_unsafe_execution_call_exists():
    offenders: list[str] = []
    importers: list[str] = []
    for path in _python_files(OCR_INFRA):
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "subprocess" for alias in node.names):
                importers.append(path.name)
            if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                offenders.append(f"{path}:from-subprocess")
            if isinstance(node, ast.Call) and _qualified_call(node) in FORBIDDEN_PROCESS_CALLS:
                offenders.append(f"{path}:{_qualified_call(node)}")
            if isinstance(node, ast.Call) and any(
                keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
                for keyword in node.keywords
            ):
                offenders.append(f"{path}:shell-true")
    assert offenders == []
    assert importers == ["process_backend.py"]


def test_process_backend_port_remains_injected_and_concrete_backend_is_not_registered():
    port_tree = _tree(OCR_INFRA / "process_port.py")
    backend_classes = [
        node for node in ast.walk(port_tree) if isinstance(node, ast.ClassDef) and node.name == "OcrProcessBackendPort"
    ]
    assert len(backend_classes) == 1
    assert any(isinstance(base, ast.Name) and base.id == "Protocol" for base in backend_classes[0].bases)

    runner_tree = _tree(OCR_INFRA / "process_runner.py")
    runner_classes = [
        node for node in ast.walk(runner_tree) if isinstance(node, ast.ClassDef) and node.name == "PolicyBoundOcrProcessRunner"
    ]
    assert len(runner_classes) == 1
    constructor = next(
        node for node in runner_classes[0].body if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    assert any(argument.arg == "backend" for argument in constructor.args.args)


def test_no_production_boundary_imports_or_registers_concrete_tesseract_adapter():
    boundary_roots = [APP / "parser", APP / "runtime", APP / "application", APP / "routes", APP / "interfaces"]
    boundary_files = [APP / "main.py"]
    for root in boundary_roots:
        boundary_files.extend(_python_files(root))
    offenders: list[str] = []
    for path in boundary_files:
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "infrastructure.ocr" in node.module:
                offenders.append(str(path.relative_to(API)))
            if isinstance(node, ast.Import) and any("infrastructure.ocr" in alias.name for alias in node.names):
                offenders.append(str(path.relative_to(API)))
            if isinstance(node, ast.Name) and node.id in {"TesseractOcrEngine", "PolicyBoundOcrProcessRunner"}:
                offenders.append(str(path.relative_to(API)))
    assert offenders == []


def test_requirements_and_locks_have_no_tesseract_runtime_dependency():
    dependency_files = sorted(API.glob("requirements*.txt")) + sorted(API.glob("*.lock"))
    contents = "\n".join(path.read_text(encoding="utf-8").lower() for path in dependency_files)
    assert "pytesseract" not in contents
    assert "tesserocr" not in contents
    assert "tesseract-ocr" not in contents


def test_docker_and_compose_do_not_install_or_execute_tesseract():
    deployment_files = [API / "Dockerfile", ROOT / "compose.yml"]
    contents = "\n".join(path.read_text(encoding="utf-8").lower() for path in deployment_files if path.exists())
    assert "tesseract" not in contents


def test_ocr_infrastructure_has_no_download_install_native_build_or_windows_runner():
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in _python_files(OCR_INFRA))
    forbidden_fragments = {
        "pip install",
        "apt install",
        "apt-get install",
        "download(",
        "urlretrieve(",
        "native build",
        "windowstesseract",
        "windowsprocessrunner",
    }
    assert all(fragment not in source for fragment in forbidden_fragments)


def test_candidate_report_keeps_runtime_and_production_disabled():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["offline_fail_closed_gate"]["status"] == "contract-defined-runtime-not-implemented"
    preflight = report["runtime_integration_preflight_gate"]
    assert preflight["status"] == "contract-defined-runtime-not-implemented"
    assert preflight["production_approval"] is False
    assert report["production_approval_gate"]["production_approval"] is False
    assert report["paddleocr_b2_decision"]["status"] == "deferred/blocked"
