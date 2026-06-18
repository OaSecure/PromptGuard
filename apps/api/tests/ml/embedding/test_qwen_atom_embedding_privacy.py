import ast
from pathlib import Path

from app.atoms import AnalysisAtom, TextRange
from app.ml.embedding import AtomEmbeddingModelLoader, AtomEmbeddingRequest, QWEN3_EMBEDDING_MODEL, embed_atoms


class FakeBackend:
    model_version = QWEN3_EMBEDDING_MODEL
    dimension = 2
    is_frozen = True

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class ExplodingBackend(FakeBackend):
    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        raise RuntimeError(f"backend saw {texts[0]} and vector [0.1, 0.2]")


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
        timeout_ms=1_000,
    )


def test_embedding_vector_not_logged(caplog):
    backend = FakeBackend()
    loader = AtomEmbeddingModelLoader(lambda model_name: backend)

    result = embed_atoms(request("private atom text"), loader)

    assert result.failure is None
    assert "[0.1, 0.2]" not in caplog.text
    assert "private atom text" not in caplog.text


def test_failure_message_does_not_include_vector_or_atom_text(caplog):
    loader = AtomEmbeddingModelLoader(lambda model_name: ExplodingBackend())

    result = embed_atoms(request("SECRET-ATOM-TEXT"), loader)

    assert result.embeddings == []
    assert result.failure is not None
    assert "SECRET-ATOM-TEXT" not in result.failure.message
    assert "[0.1, 0.2]" not in result.failure.message
    assert "SECRET-ATOM-TEXT" not in caplog.text
    assert "[0.1, 0.2]" not in caplog.text


def test_embedding_vector_not_in_safe_metadata():
    loader = AtomEmbeddingModelLoader(lambda model_name: FakeBackend())

    result = embed_atoms(request("private atom text"), loader)
    payload = result.safe_metadata()

    assert set(payload) == {"embedding_model_version", "dimension", "normalized", "embedding_count", "failure_code"}
    assert "private atom text" not in str(payload)
    assert "0.1" not in str(payload)
    assert "0.2" not in str(payload)


def test_embedding_worker_does_not_import_scanner_classifier_policy():
    package_root = Path(__file__).resolve().parents[3] / "app" / "ml" / "embedding"
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
