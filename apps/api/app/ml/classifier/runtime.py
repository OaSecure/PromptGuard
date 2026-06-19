import math

from app.atoms.models import PipelineFailure
from app.ml.classifier.models import (
    ProbabilityPredictor,
    SegmentClassificationCandidate,
    SegmentClassificationRequest,
    SegmentClassificationResult,
)
from app.ml.segment_embedding.models import SegmentEmbedding


class LrClassifierRuntime:
    def __init__(self, predictor: ProbabilityPredictor) -> None:
        self._predictor = predictor

    def classify(self, request: SegmentClassificationRequest) -> SegmentClassificationResult:
        failure = self._validate_predictor_labels(request)
        if failure is not None:
            return self._failed(request.input_id, failure)

        if not request.segment_embeddings:
            return SegmentClassificationResult(input_id=request.input_id)

        failure = self._validate_segment_embeddings(request.segment_embeddings)
        if failure is not None:
            return self._failed(request.input_id, failure)

        vectors = [item.vector for item in request.segment_embeddings]
        try:
            score_rows = self._predictor.predict_probabilities(vectors)
        except Exception:
            return self._failed(
                request.input_id,
                PipelineFailure(code="CLASSIFIER_PREDICTOR_FAILED", message="classifier predictor failed closed"),
            )

        failure = self._validate_score_rows(score_rows, len(request.segment_embeddings), len(request.artifact.target_labels))
        if failure is not None:
            return self._failed(request.input_id, failure)

        candidates: list[SegmentClassificationCandidate] = []
        for segment_embedding, score_row in zip(request.segment_embeddings, score_rows):
            for label, score in zip(request.artifact.target_labels, score_row):
                if score >= request.artifact.candidate_threshold:
                    candidates.append(
                        SegmentClassificationCandidate(
                            segment_id=segment_embedding.segment_id,
                            label=label,
                            score=score,
                            threshold=request.artifact.candidate_threshold,
                            artifact_id=request.artifact.artifact_id,
                            runtime_version=request.artifact.runtime_version,
                        )
                    )

        return SegmentClassificationResult(input_id=request.input_id, candidates=candidates)

    def _validate_predictor_labels(self, request: SegmentClassificationRequest) -> PipelineFailure | None:
        if list(self._predictor.target_labels) != request.artifact.target_labels:
            return PipelineFailure(
                code="CLASSIFIER_LABEL_MISMATCH",
                message="classifier predictor labels do not match artifact labels",
                metadata={"artifact_id": request.artifact.artifact_id},
            )
        return None

    def _validate_segment_embeddings(self, segment_embeddings: list[SegmentEmbedding]) -> PipelineFailure | None:
        expected_dimension: int | None = None
        for item in segment_embeddings:
            if not item.vector or item.dimension != len(item.vector):
                return PipelineFailure(code="CLASSIFIER_INVALID_SEGMENT_VECTOR", message="classifier segment vector is invalid")
            if expected_dimension is None:
                expected_dimension = item.dimension
            elif item.dimension != expected_dimension:
                return PipelineFailure(code="CLASSIFIER_INVALID_SEGMENT_VECTOR", message="classifier segment vector dimension mismatch")
            if any(not math.isfinite(value) for value in item.vector):
                return PipelineFailure(code="CLASSIFIER_INVALID_SEGMENT_VECTOR", message="classifier segment vector is invalid")
        return None

    def _validate_score_rows(
        self,
        score_rows: list[list[float]],
        expected_rows: int,
        expected_columns: int,
    ) -> PipelineFailure | None:
        if len(score_rows) != expected_rows:
            return PipelineFailure(code="CLASSIFIER_SCORE_SHAPE_MISMATCH", message="classifier score row count mismatch")

        for row in score_rows:
            if len(row) != expected_columns:
                return PipelineFailure(code="CLASSIFIER_SCORE_SHAPE_MISMATCH", message="classifier score label count mismatch")
            if any(not math.isfinite(score) or score < 0.0 or score > 1.0 for score in row):
                return PipelineFailure(code="CLASSIFIER_INVALID_SCORE", message="classifier score is invalid")
        return None

    def _failed(self, input_id: str, failure: PipelineFailure) -> SegmentClassificationResult:
        return SegmentClassificationResult(input_id=input_id, candidates=[], failure=failure)
