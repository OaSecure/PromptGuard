from typing import Protocol

from app.atoms.models import PipelineFailure
from app.ml.classifier.models import SegmentClassificationRequest, SegmentClassificationResult


class ClassifierRuntime(Protocol):
    def classify(self, request: SegmentClassificationRequest) -> SegmentClassificationResult:
        ...


class ClassifierService:
    def __init__(self, runtime: ClassifierRuntime) -> None:
        self._runtime = runtime

    def classify(self, request: SegmentClassificationRequest) -> SegmentClassificationResult:
        try:
            return self._runtime.classify(request)
        except Exception:
            return SegmentClassificationResult(
                input_id=request.input_id,
                failure=PipelineFailure(
                    code="CLASSIFIER_SERVICE_FAILED",
                    message="classifier service failed closed",
                ),
            )
