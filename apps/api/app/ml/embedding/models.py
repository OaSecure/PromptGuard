from typing import Literal

from pydantic import BaseModel

from app.atoms.models import AnalysisAtom, PipelineFailure

QWEN3_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
Qwen3EmbeddingModelName = Literal["Qwen/Qwen3-Embedding-0.6B"]


class AtomEmbeddingRequest(BaseModel):
    input_id: str
    atoms: list[AnalysisAtom]
    model_name: Qwen3EmbeddingModelName = QWEN3_EMBEDDING_MODEL
    normalize_vectors: bool = True
    timeout_ms: int = 30_000


class AtomEmbedding(BaseModel):
    atom_id: str
    vector: list[float]


class AtomEmbeddingResult(BaseModel):
    input_id: str
    embeddings: list[AtomEmbedding]
    embedding_model_version: str
    dimension: int
    normalized: bool
    failure: PipelineFailure | None = None

    def safe_metadata(self) -> dict[str, object]:
        return {
            "embedding_model_version": self.embedding_model_version,
            "dimension": self.dimension,
            "normalized": self.normalized,
            "embedding_count": len(self.embeddings),
            "failure_code": None if self.failure is None else self.failure.code,
        }
