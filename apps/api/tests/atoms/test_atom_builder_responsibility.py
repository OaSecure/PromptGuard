import ast
import sys
from pathlib import Path

import pytest

from app.atoms import AtomBuildRequest, AtomizationPolicy, ParsedBlock, ParsedDocument, build_atoms


FORBIDDEN_IMPORT_PARTS = {
    "scanner",
    "normalizer",
    "embedding",
    "segmenter",
    "classifier",
    "verifier",
    "policy",
}


def _atoms_package_path() -> Path:
    return Path(__file__).parents[2] / "app" / "atoms"


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_atoms_package_source_does_not_import_forbidden_modules_with_ast():
    for path in _atoms_package_path().rglob("*.py"):
        imports = _imported_module_names(path)
        forbidden = {
            module
            for module in imports
            if any(part in module.lower().split(".") for part in FORBIDDEN_IMPORT_PARTS)
        }
        assert forbidden == set(), f"{path} imports forbidden modules: {sorted(forbidden)}"


def _document() -> ParsedDocument:
    return ParsedDocument(
        input_id="input-1",
        blocks=[
            ParsedBlock(
                block_id="block-1",
                input_id="input-1",
                text="scan keyword should remain plain atom text",
                source_type="text",
                location=None,
                metadata={},
            )
        ],
    )


def _assert_forbidden_modules_not_loaded(forbidden_parts: set[str]):
    loaded = [name for name in sys.modules if any(part in name.lower() for part in forbidden_parts)]
    assert loaded == []


@pytest.mark.parametrize(
    "forbidden_parts",
    [
        {"scanner"},
        {"normalizer"},
        {"embedding"},
        {"segmenter"},
        {"classifier", "verifier", "policy"},
    ],
)
def test_atom_builder_does_not_call_forbidden_pipeline_modules(forbidden_parts: set[str]):
    before = set(sys.modules)

    result = build_atoms(AtomBuildRequest(document=_document(), policy=AtomizationPolicy()))

    assert result.atoms
    newly_loaded = set(sys.modules) - before
    assert [name for name in newly_loaded if any(part in name.lower() for part in forbidden_parts)] == []


def test_atom_builder_does_not_scan_keywords():
    before = set(sys.modules)

    build_atoms(AtomBuildRequest(document=_document(), policy=AtomizationPolicy()))

    assert [name for name in set(sys.modules) - before if "scanner" in name.lower()] == []


def test_atom_builder_does_not_call_normalizer():
    before = set(sys.modules)

    build_atoms(AtomBuildRequest(document=_document(), policy=AtomizationPolicy()))

    assert [name for name in set(sys.modules) - before if "normalizer" in name.lower()] == []


def test_atom_builder_does_not_call_embedding_worker():
    before = set(sys.modules)

    build_atoms(AtomBuildRequest(document=_document(), policy=AtomizationPolicy()))

    assert [name for name in set(sys.modules) - before if "embedding" in name.lower()] == []


def test_atom_builder_does_not_call_segmenter():
    before = set(sys.modules)

    build_atoms(AtomBuildRequest(document=_document(), policy=AtomizationPolicy()))

    assert [name for name in set(sys.modules) - before if "segmenter" in name.lower()] == []


def test_atom_builder_does_not_call_classifier_verifier_or_policy():
    before = set(sys.modules)

    build_atoms(AtomBuildRequest(document=_document(), policy=AtomizationPolicy()))

    forbidden = {"classifier", "verifier", "policy"}
    assert [name for name in set(sys.modules) - before if any(part in name.lower() for part in forbidden)] == []
