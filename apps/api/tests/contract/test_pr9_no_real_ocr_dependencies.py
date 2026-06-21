import ast
import re
from pathlib import Path


API_ROOT = Path(__file__).parents[2]
FORBIDDEN = {"paddleocr", "paddle", "paddlepaddle", "pytesseract", "fitz", "pdf2image"}
PARSER_FAILURE_CODES = {
    "PDF_RENDER_FAILED",
    "OCR_ENGINE_UNAVAILABLE",
    "OCR_TIMEOUT",
    "OCR_FAILED",
    "OCR_NO_TEXT_DETECTED",
    "OCR_PAGE_LIMIT_EXCEEDED",
}


def test_default_core_requirements_have_no_real_ocr_dependency():
    requirements = (API_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert all(name not in requirements for name in FORBIDDEN)


def test_parser_core_has_no_concrete_ocr_or_renderer_import():
    imported = set()
    for path in (API_ROOT / "app" / "parser").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN)


def test_pr9_ocr_failure_codes_use_parser_failure_registry():
    source_paths = [
        API_ROOT / "app" / "parser" / "adapters" / "pdf_ocr_fake.py",
        API_ROOT / "app" / "parser" / "fakes.py",
    ]
    used = set()
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        used.update(re.findall(r'"((?:PDF|OCR)_[A-Z_]+)"', source))
    assert used <= PARSER_FAILURE_CODES
