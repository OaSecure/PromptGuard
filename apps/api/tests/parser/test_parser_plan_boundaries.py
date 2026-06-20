import ast
from pathlib import Path

from app.parser.models import FileParserResult


def _source(name):
    return (Path(__file__).parents[2] / "app" / "parser" / name).read_text(encoding="utf-8")


def _imports(name):
    tree = ast.parse(_source(name))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_parser_plan_executor_does_not_emit_policy_decision():
    assert set(FileParserResult.model_fields).isdisjoint(
        {"action", "recommended_action", "reason_code", "user_notice"}
    )


def test_parser_plan_executor_does_not_call_scanner():
    assert all("scanner" not in item.lower() for item in _imports("executor.py"))


def test_parser_plan_resolver_does_not_parse_or_ocr():
    source = _source("planning.py").lower()
    forbidden_calls = (".parse(", ".recognize(", ".execute(")
    assert all(call not in source for call in forbidden_calls)


def test_parser_plan_modules_have_no_forbidden_imports():
    imports = _imports("planning.py") | _imports("executor.py")
    forbidden = {
        "pypdf", "pypdfium2", "paddleocr", "pytesseract", "docx", "openpyxl", "pptx",
        "app.routes", "app.db", "app.events", "app.scanner", "app.normalization",
        "app.ml", "app.policy", "app.masking",
    }
    assert not {item for item in imports if any(item == value or item.startswith(value + ".") for value in forbidden)}
