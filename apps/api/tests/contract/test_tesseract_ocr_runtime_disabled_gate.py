import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[4]
API = ROOT / "apps" / "api"
APP = API / "app"


def test_production_boundaries_do_not_register_real_tesseract_backend():
    roots = [APP / "parser", APP / "runtime", APP / "application", APP / "routes", APP / "interfaces"]
    files = [APP / "main.py"]
    for root in roots:
        files.extend(root.rglob("*.py"))
    offenders = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and "process_backend" in ast.unparse(node):
                offenders.append(str(path.relative_to(API)))
            if isinstance(node, ast.Name) and node.id == "SubprocessOcrProcessBackend":
                offenders.append(str(path.relative_to(API)))
    assert offenders == []


def test_readiness_artifacts_remain_not_production_ready():
    report = json.loads((ROOT / "third_party/licenses/tesseract_ocr_candidate_report.json").read_text(encoding="utf-8"))
    evidence = json.loads(
        (ROOT / "third_party/licenses/tesseract_isolated_validation_evidence.json").read_text(encoding="utf-8")
    )
    assert report["approved_for_dependency_addition"] is False
    assert report["approved_for_default_distribution"] is False
    assert report["production_approval_gate"]["production_approval"] is False
    assert evidence["production_approval"] is False
