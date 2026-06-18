import ast
from pathlib import Path

from app.atoms import TextRange
from app.ml.embedding import AtomEmbedding
from app.ml.segment_embedding import (
    SegmentEmbeddingBuildRequest,
    SegmentEmbeddingPolicy,
    build_segment_embeddings,
    project_segment_embedding_result_metadata,
)
from app.segmenter import AnalysisSegment


def segment() -> AnalysisSegment:
    return AnalysisSegment(
        segment_id="s1",
        input_id="input-1",
        atom_ids=["a1"],
        text="SECRET-SEGMENT-TEXT",
        original_range=TextRange(start=0, end=19),
        locations=[],
        segment_type="semantic",
        ordinal=0,
    )


def test_segment_embedding_not_persisted():
    result = build_segment_embeddings(
        SegmentEmbeddingBuildRequest(
            input_id="input-1",
            segments=[segment()],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[0.12345, 0.98765])],
            embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
            policy=SegmentEmbeddingPolicy(),
        )
    )

    payload = project_segment_embedding_result_metadata(result)

    assert "SECRET-SEGMENT-TEXT" not in str(payload)
    assert "0.12345" not in str(payload)
    assert "0.98765" not in str(payload)
    assert "vector" not in str(payload)


def test_segment_embedding_metadata_uses_safe_allowlist():
    result = build_segment_embeddings(
        SegmentEmbeddingBuildRequest(
            input_id="input-1",
            segments=[segment()],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[1.0, 0.0])],
            embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
            policy=SegmentEmbeddingPolicy(),
        )
    )

    payload = project_segment_embedding_result_metadata(result)

    assert set(payload) == {"segment_embeddings", "failure"}
    assert set(payload["segment_embeddings"][0]) == {
        "segment_id",
        "dimension",
        "pooling",
        "normalized",
        "embedding_model_version",
    }


def test_segment_embedding_output_has_no_classifier_policy_or_response_fields():
    result = build_segment_embeddings(
        SegmentEmbeddingBuildRequest(
            input_id="input-1",
            segments=[segment()],
            atom_embeddings=[AtomEmbedding(atom_id="a1", vector=[1.0, 0.0])],
            embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
            policy=SegmentEmbeddingPolicy(),
        )
    )

    payload = result.model_dump()
    forbidden = {
        "action",
        "recommended_action",
        "reason_code",
        "user_notice",
        "user_notices",
        "label_scores",
        "predicted_labels",
        "thresholded_labels",
        "classifier_artifact",
        "verification",
        "policy_decision",
        "api_response",
    }

    assert "failure" in payload
    assert "failures" not in payload
    assert not any(field in str(payload) for field in forbidden)


def test_segment_embedding_builder_does_not_import_forbidden_modules():
    package_root = Path(__file__).resolve().parents[3] / "app" / "ml" / "segment_embedding"
    forbidden = {"scanner", "classifier", "verifier", "policy", "parser", "normalizer", "mapper"}

    for path in package_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert not any(any(part == forbidden_name for part in name.split(".")) for name in imports for forbidden_name in forbidden)
