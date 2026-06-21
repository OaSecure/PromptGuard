import ast
from pathlib import Path


API_ROOT = Path(__file__).parents[2]
FORBIDDEN = {"paddleocr", "pytesseract", "pypdfium2", "fitz", "pdf2image"}


def test_pr9_adds_no_real_ocr_or_pdf_renderer_dependency():
    requirements = (API_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert all(name not in requirements for name in FORBIDDEN)


def test_parser_source_has_no_real_ocr_or_renderer_import():
    imported = set()
    for path in (API_ROOT / "app" / "parser").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN)
