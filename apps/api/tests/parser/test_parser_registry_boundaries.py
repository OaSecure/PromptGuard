import ast
from pathlib import Path


def _imports(filename):
    path = Path(__file__).parents[2] / "app" / "parser" / filename
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_registry_and_executor_do_not_import_concrete_parser_or_forbidden_modules():
    imports = _imports("registry.py") | _imports("executor.py")
    forbidden = {
        "pypdf", "pypdfium2", "paddleocr", "pytesseract", "docx", "openpyxl", "pptx",
        "app.routes", "app.db", "app.events", "app.scanner", "app.normalization",
        "app.ml", "app.policy", "app.masking",
    }
    assert not {name for name in imports if any(name == item or name.startswith(item + ".") for item in forbidden)}


def test_registry_does_not_execute_adapter_during_selection():
    source = (Path(__file__).parents[2] / "app" / "parser" / "registry.py").read_text(encoding="utf-8")
    assert ".execute_step(" not in source
