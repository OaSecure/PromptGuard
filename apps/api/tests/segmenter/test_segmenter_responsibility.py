import ast
import sys
from pathlib import Path

from app.atoms import AnalysisAtom, TextRange
from app.segmenter import AtomEmbedding, SegmentBuildRequest, SegmentPolicy, build_segments


FORBIDDEN_IMPORT_PARTS = {"scanner", "normalizer", "embedding_worker", "mapper", "classifier", "verifier", "policy"}


def atom() -> AnalysisAtom:
    return AnalysisAtom(
        atom_id="a1",
        input_id="input-1",
        block_id="block-1",
        text="keyword SECRET",
        original_range=TextRange(start=0, end=14),
        location=None,
        atom_type="paragraph",
        ordinal=0,
    )


def test_segmenter_does_not_rescan_keywords():
    before = set(sys.modules)

    build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=[atom()],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[1.0, 0.0])],
            segment_policy=SegmentPolicy(),
        )
    )

    loaded = set(sys.modules) - before
    assert [name for name in loaded if "scanner" in name.lower()] == []


def test_segmenter_does_not_create_signals():
    result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=[atom()],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[1.0, 0.0])],
            segment_policy=SegmentPolicy(),
        )
    )

    assert "signals" not in str(result.model_dump())


def test_segmenter_package_does_not_import_forbidden_modules_with_ast():
    package_dir = Path(__file__).parents[2] / "app" / "segmenter"

    for path in package_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        forbidden = {
            module
            for module in imports
            if any(part in module.lower().split(".") for part in FORBIDDEN_IMPORT_PARTS)
        }
        assert forbidden == set(), f"{path} imports forbidden modules: {sorted(forbidden)}"
