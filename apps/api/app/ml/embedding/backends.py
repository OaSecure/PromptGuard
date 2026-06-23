import math

from app.ml.embedding.models import QWEN3_EMBEDDING_MODEL


class Qwen3EmbeddingBackend:
    model_version: str
    is_frozen = True

    def __init__(
        self,
        model_name: str = QWEN3_EMBEDDING_MODEL,
        *,
        device: str | None = None,
        trust_remote_code: bool = False,
    ) -> None:
        self.model_version = model_name
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("qwen3_embedding_dependencies_unavailable") from exc

        selected_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = SentenceTransformer(model_name, device=selected_device, trust_remote_code=trust_remote_code)
        self._model.eval()
        for parameter in self._model.parameters():
            parameter.requires_grad_(False)

        dimension = self._model.get_sentence_embedding_dimension()
        if dimension is None:
            raise RuntimeError("qwen3_embedding_dependencies_unavailable")
        self.dimension = int(dimension)

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        if not texts:
            return []

        vectors = self._model.encode(
            texts,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in vectors.tolist()]


def create_qwen3_backend(model_name: str = QWEN3_EMBEDDING_MODEL) -> Qwen3EmbeddingBackend:
    return Qwen3EmbeddingBackend(model_name)


def vector_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))
