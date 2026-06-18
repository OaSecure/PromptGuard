import builtins
import os

import pytest

from app.atoms import AnalysisAtom, TextRange
from app.ml.embedding import (
    AtomEmbeddingModelLoader,
    AtomEmbeddingRequest,
    QWEN3_EMBEDDING_MODEL,
    Qwen3EmbeddingBackend,
    create_qwen3_backend,
    embed_atoms,
)
from app.ml.embedding.backends import vector_norm
from app.segmenter import SegmentBuildRequest, SegmentPolicy, build_segments


def atom(text: str) -> AnalysisAtom:
    return AnalysisAtom(
        atom_id="a1",
        input_id="input-1",
        block_id="block-1",
        text=text,
        original_range=TextRange(start=0, end=len(text)),
        location=None,
        atom_type="paragraph",
        ordinal=0,
    )


def request(text: str) -> AtomEmbeddingRequest:
    return AtomEmbeddingRequest(
        input_id="input-1",
        atoms=[atom(text)],
        model_name=QWEN3_EMBEDDING_MODEL,
        normalize_vectors=True,
        timeout_ms=120_000,
    )


def test_qwen3_backend_dependency_failure_is_sanitized(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"torch", "transformers"}:
            raise ImportError(f"missing {name} while handling SECRET-ATOM")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    with pytest.raises(RuntimeError) as exc_info:
        Qwen3EmbeddingBackend(QWEN3_EMBEDDING_MODEL)

    assert str(exc_info.value) == "qwen3_embedding_dependencies_unavailable"
    assert "SECRET-ATOM" not in str(exc_info.value)


def test_qwen3_backend_factory_integrates_with_worker_without_leaking_text(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"torch", "transformers"}:
            raise ImportError("optional ml dependency missing for SECRET-ATOM")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    loader = AtomEmbeddingModelLoader(create_qwen3_backend)

    result = embed_atoms(request("SECRET-ATOM"), loader)

    assert result.embeddings == []
    assert result.failure is not None
    assert result.failure.code == "EMBEDDING_MODEL_UNAVAILABLE"
    assert "SECRET-ATOM" not in result.failure.message


@pytest.mark.skipif(os.getenv("RUN_REAL_QWEN_TESTS") != "1", reason="real Qwen3 model download is opt-in")
def test_real_qwen3_backend_embeds_atom_text_when_opted_in():
    loader = AtomEmbeddingModelLoader(create_qwen3_backend)

    result = embed_atoms(request("PromptGuard atom embedding smoke test"), loader)

    assert result.failure is None
    assert len(result.embeddings) == 1
    assert result.dimension > 0
    assert len(result.embeddings[0].vector) == result.dimension
    assert 0.99 <= vector_norm(result.embeddings[0].vector) <= 1.01


@pytest.mark.skipif(os.getenv("RUN_REAL_QWEN_TESTS") != "1", reason="real Qwen3 model download is opt-in")
def test_real_qwen3_embeddings_feed_adjacent_segmenter_when_opted_in():
    atoms = [
        atom("Payment terms and contract renewal details."),
        AnalysisAtom(
            atom_id="a2",
            input_id="input-1",
            block_id="block-1",
            text="OAuth token leakage and credential exposure risk.",
            original_range=TextRange(start=42, end=91),
            location=None,
            atom_type="paragraph",
            ordinal=1,
        ),
    ]
    loader = AtomEmbeddingModelLoader(create_qwen3_backend)

    embedding_result = embed_atoms(
        AtomEmbeddingRequest(
            input_id="input-1",
            atoms=atoms,
            model_name=QWEN3_EMBEDDING_MODEL,
            normalize_vectors=True,
            timeout_ms=120_000,
        ),
        loader,
    )
    segment_result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=atoms,
            atom_embeddings=embedding_result.embeddings,
            segment_policy=SegmentPolicy(cosine_break_threshold=0.72),
        )
    )

    assert embedding_result.failure is None
    assert segment_result.failure is None
    assert len(embedding_result.embeddings) == 2
    assert len(segment_result.boundary_scores) == 1
