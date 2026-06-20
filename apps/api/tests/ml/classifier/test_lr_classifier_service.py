from app.atoms.models import PipelineFailure
from app.ml.classifier import ClassifierArtifactRef, SegmentClassificationRequest
from app.ml.classifier.service import ClassifierService
from app.ml.segment_embedding import SegmentEmbedding


class FakeRuntime:
    def __init__(self, failure: PipelineFailure | None = None, raises: Exception | None = None) -> None:
        self.seen_request: SegmentClassificationRequest | None = None
        self._failure = failure
        self._raises = raises

    def classify(self, request: SegmentClassificationRequest):
        self.seen_request = request
        if self._raises is not None:
            raise self._raises
        from app.ml.classifier import SegmentClassificationResult

        return SegmentClassificationResult(input_id=request.input_id, failure=self._failure)


def artifact() -> ClassifierArtifactRef:
    return ClassifierArtifactRef(
        artifact_id="lr-v205",
        manifest_version="v205",
        runtime_version="lr-runtime-v1",
        target_labels=["secret", "credential"],
        candidate_threshold=0.575,
        embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
    )


def request(input_id: str = "input-1") -> SegmentClassificationRequest:
    return SegmentClassificationRequest(
        input_id=input_id,
        segment_embeddings=[
            SegmentEmbedding(
                segment_id="s1",
                vector=[0.1, 0.2],
                embedding_model_version="Qwen/Qwen3-Embedding-0.6B",
                dimension=2,
                pooling="mean",
                normalized=True,
            )
        ],
        artifact=artifact(),
    )


def test_classifier_service_delegates_to_supplied_runtime():
    runtime = FakeRuntime()
    service = ClassifierService(runtime)
    classification_request = request()

    result = service.classify(classification_request)

    assert runtime.seen_request == classification_request
    assert result.input_id == "input-1"
    assert result.candidates == []
    assert result.failure is None


def test_classifier_service_preserves_runtime_failure_result():
    runtime = FakeRuntime(failure=PipelineFailure(code="CLASSIFIER_LABEL_MISMATCH", message="safe failure"))
    service = ClassifierService(runtime)

    result = service.classify(request())

    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_LABEL_MISMATCH"
    assert result.candidates == []


def test_classifier_service_fails_closed_without_sensitive_exception_values():
    runtime = FakeRuntime(
        raises=RuntimeError(
            "SENSITIVE_PROMPT_SENTINEL "
            "SENSITIVE_FILE_CONTENT_SENTINEL "
            "SENSITIVE_EXTRACTED_TEXT_SENTINEL "
            "SENSITIVE_DETECTED_VALUE_SENTINEL "
            "SENSITIVE_FILENAME_SENTINEL "
            "0.12345"
        )
    )
    service = ClassifierService(runtime)

    result = service.classify(request(input_id="input-1"))
    rendered = str(result.model_dump())

    assert result.input_id == "input-1"
    assert result.candidates == []
    assert result.failure is not None
    assert result.failure.code == "CLASSIFIER_SERVICE_FAILED"
    assert result.failure.metadata == {}
    assert "SENSITIVE_PROMPT_SENTINEL" not in str(result.failure)
    assert "SENSITIVE_FILE_CONTENT_SENTINEL" not in rendered
    assert "SENSITIVE_EXTRACTED_TEXT_SENTINEL" not in rendered
    assert "SENSITIVE_DETECTED_VALUE_SENTINEL" not in rendered
    assert "SENSITIVE_FILENAME_SENTINEL" not in rendered
    assert "0.12345" not in rendered
