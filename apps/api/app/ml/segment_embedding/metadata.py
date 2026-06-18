from typing import Any

from app.ml.segment_embedding.models import SegmentEmbedding, SegmentEmbeddingBuildResult


def project_segment_embedding_metadata(segment_embedding: SegmentEmbedding) -> dict[str, Any]:
    return {
        "segment_id": segment_embedding.segment_id,
        "dimension": segment_embedding.dimension,
        "pooling": segment_embedding.pooling,
        "normalized": segment_embedding.normalized,
        "embedding_model_version": segment_embedding.embedding_model_version,
    }


def project_segment_embedding_result_metadata(result: SegmentEmbeddingBuildResult) -> dict[str, Any]:
    return {
        "segment_embeddings": [
            project_segment_embedding_metadata(segment_embedding)
            for segment_embedding in result.segment_embeddings
        ],
        "failure": None if result.failure is None else {"failure_code": result.failure.code},
    }
