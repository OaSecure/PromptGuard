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
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("qwen3_embedding_dependencies_unavailable") from exc

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=trust_remote_code)
        self._model = AutoModel.from_pretrained(model_name, trust_remote_code=trust_remote_code)
        self._model.eval()
        for parameter in self._model.parameters():
            parameter.requires_grad_(False)

        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        self.dimension = int(getattr(self._model.config, "hidden_size"))

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        if not texts:
            return []

        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        encoded = {key: value.to(self._device) for key, value in encoded.items()}
        with self._torch.no_grad():
            outputs = self._model(**encoded)

        vectors = _last_token_pool(outputs.last_hidden_state, encoded["attention_mask"])
        if normalize:
            vectors = self._torch.nn.functional.normalize(vectors, p=2, dim=1)
        return vectors.detach().cpu().float().tolist()


def create_qwen3_backend(model_name: str = QWEN3_EMBEDDING_MODEL) -> Qwen3EmbeddingBackend:
    return Qwen3EmbeddingBackend(model_name)


def _last_token_pool(last_hidden_states, attention_mask):
    sequence_lengths = attention_mask.sum(dim=1) - 1
    batch_size = last_hidden_states.shape[0]
    batch_indexes = last_hidden_states.new_tensor(range(batch_size), dtype=sequence_lengths.dtype).long()
    return last_hidden_states[batch_indexes, sequence_lengths]


def vector_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))
