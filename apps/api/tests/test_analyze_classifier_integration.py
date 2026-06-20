import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.atoms.models import PipelineFailure
from app.ml.classifier.factory import (
    BuiltClassifierService,
    ClassifierRuntimeProviderResult,
    build_classifier_service_from_manifest,
)
from app.ml.classifier.models import (
    ClassifierArtifactRef,
    SegmentClassificationCandidate,
    SegmentClassificationResult,
)
from app.ml.classifier.runtime import LrClassifierRuntime
from app.ml.classifier.service import ClassifierService
from app.ml.embedding.loader import AtomEmbeddingModelLoader
from app.ml.verifier import (
    RobertaVerificationEvidence,
    RobertaVerificationResult,
    RobertaVerifierService,
    VerifierArtifactRef,
)
from app.routes import analyze as analyze_route
from app.routes.auth import get_db_session
from app.services.analyze_classifier import AnalyzeVerifierConfig, evaluate_analyze_classifier

try:
    from apps.api.tests.test_analyze import (
        _FakeSession,
        _analyze_payload,
        _bearer_header,
        _filter_rule,
        _text_input,
        _user,
    )
except ModuleNotFoundError:
    from tests.test_analyze import (
        _FakeSession,
        _analyze_payload,
        _bearer_header,
        _filter_rule,
        _text_input,
        _user,
    )


def _client(user=None, rules=None, provider=None, verifier_config=None) -> tuple[TestClient, _FakeSession]:
    app = FastAPI()
    app.include_router(analyze_route.router)
    fake_session = _FakeSession(user, rules)

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(_request, exc):
        safe_errors = [
            {
                "loc": error.get("loc", ()),
                "msg": error.get("msg", "Invalid request"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    async def override_session():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_session
    classifier_provider_dependency = getattr(analyze_route, "get_classifier_runtime_provider", None)
    if classifier_provider_dependency is not None and provider is not None:
        app.dependency_overrides[classifier_provider_dependency] = lambda: provider
    embedding_loader_dependency = getattr(analyze_route, "get_atom_embedding_loader", None)
    if embedding_loader_dependency is not None:
        app.dependency_overrides[embedding_loader_dependency] = lambda: None
    verifier_dependency = getattr(analyze_route, "get_analyze_verifier_config", None)
    if verifier_dependency is not None:
        app.dependency_overrides[verifier_dependency] = lambda: verifier_config
    return TestClient(app), fake_session


def _disabled_provider() -> ClassifierRuntimeProviderResult:
    return ClassifierRuntimeProviderResult(
        failure=PipelineFailure(
            code="CLASSIFIER_RUNTIME_DISABLED",
            message="classifier runtime disabled",
            metadata={"status": "disabled"},
        )
    )


def _enabled_provider() -> ClassifierRuntimeProviderResult:
    return ClassifierRuntimeProviderResult(bundle=SimpleNamespace(service=object(), artifact=object()))


def _stored_payload(fake_session: _FakeSession) -> str:
    rows = [getattr(item, "__dict__", {}) for item in fake_session.added]
    return json.dumps(rows, default=str)


class _FakeEmbeddingBackend:
    model_version = "fake-embedding-v1"
    dimension = 2
    is_frozen = True

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]


class _RecordingEmbeddingBackend:
    model_version = "fake-embedding-v1"
    dimension = 2
    is_frozen = True

    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        self.seen_texts.extend(texts)
        return [[1.0, 0.0] if "Project Atlas" in text else [0.0, 1.0] for text in texts]


class _FixedDimensionEmbeddingBackend:
    is_frozen = True

    def __init__(self, dimension: int, model_version: str) -> None:
        self.dimension = dimension
        self.model_version = model_version

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        vector = [1.0] + [0.0] * (self.dimension - 1)
        return [vector for _text in texts]


class _CandidateRuntime:
    def classify(self, request):
        return SegmentClassificationResult(
            input_id=request.input_id,
            candidates=[
                SegmentClassificationCandidate(
                    segment_id=request.segment_embeddings[0].segment_id,
                    label="secret_risk",
                    score=0.91,
                    threshold=request.artifact.candidate_threshold,
                    artifact_id=request.artifact.artifact_id,
                    runtime_version=request.artifact.runtime_version,
                )
            ],
        )


class _NoCandidateRuntime:
    def classify(self, request):
        return SegmentClassificationResult(input_id=request.input_id)


class _RecordingProbabilityPredictor:
    target_labels = ["secret_risk"]

    def __init__(self) -> None:
        self.seen_vectors: list[list[float]] = []

    def predict_probabilities(self, vectors: list[list[float]]) -> list[list[float]]:
        self.seen_vectors.extend(vectors)
        return [[0.92] for _vector in vectors]


def _artifact() -> ClassifierArtifactRef:
    return ClassifierArtifactRef(
        artifact_id="fake-lr-artifact",
        manifest_version="1",
        runtime_version="lr-runtime-test",
        target_labels=["secret_risk"],
        candidate_threshold=0.8,
        embedding_model_version="fake-embedding-v1",
    )


def _verifier_artifact() -> VerifierArtifactRef:
    return VerifierArtifactRef(
        artifact_id="fake-verifier-artifact",
        model_version="fake-roberta-v1",
        runtime_version="verifier-runtime-test",
    )


def _provider_with_runtime(runtime) -> ClassifierRuntimeProviderResult:
    return ClassifierRuntimeProviderResult(
        bundle=BuiltClassifierService(
            service=ClassifierService(runtime),
            artifact=_artifact(),
        )
    )


class _RecordingVerifierModel:
    def __init__(self) -> None:
        self.requests = []

    def verify(self, request):
        self.requests.append(request)
        return RobertaVerificationResult(
            input_id=request.input_id,
            verifications=[
                RobertaVerificationEvidence(
                    segment_id=request.candidates[0].segment_id,
                    candidate_label=request.candidates[0].candidate_label,
                    verifier_status="confirmed",
                    accepted=True,
                    confidence=0.96,
                    reason_code_candidates=["VERIFIER_CONFIRMED"],
                    verifier_model_version="fake-roberta-v1",
                )
            ],
        )


class _FailingVerifierModel:
    def verify(self, request):
        raise RuntimeError("raw verifier failure sentinel must not leak")


def _trained_artifact_zip_path_or_skip() -> Path:
    configured_path = os.environ.get("PROMPTGUARD_TEST_CLASSIFIER_ARTIFACT_ZIP")
    if not configured_path:
        pytest.skip("set PROMPTGUARD_TEST_CLASSIFIER_ARTIFACT_ZIP to run the trained classifier artifact smoke test")

    artifact_zip_path = Path(configured_path)
    if not artifact_zip_path.is_absolute():
        artifact_zip_path = (Path.cwd() / artifact_zip_path).resolve()
    if not artifact_zip_path.is_file():
        pytest.skip("configured trained classifier artifact zip was not found")
    return artifact_zip_path


def _trained_joblib_vector_dimension(joblib_path: Path) -> int:
    joblib = pytest.importorskip("joblib")
    payload = joblib.load(joblib_path)
    classifier = payload.get("classifier") if isinstance(payload, dict) else None
    dimension = getattr(classifier, "n_features_in_", None)
    if dimension is None and hasattr(classifier, "coef_"):
        dimension = classifier.coef_.shape[1]
    assert isinstance(dimension, int) and dimension > 0
    return dimension


def test_evaluate_analyze_classifier_uses_pipeline_and_reports_candidates() -> None:
    loader = AtomEmbeddingModelLoader(lambda _model_name: _FakeEmbeddingBackend())
    provider = _provider_with_runtime(_CandidateRuntime())
    text_inputs = [(0, SimpleNamespace(input_id="in_1", source="composer", content="ordinary implementation note"))]

    outcome = evaluate_analyze_classifier(text_inputs, provider, loader)

    assert outcome.enabled is True
    assert outcome.has_candidates is True
    assert outcome.failure is None


def test_evaluate_analyze_classifier_embeds_sentence_and_classifies_with_lr_runtime() -> None:
    backend = _RecordingEmbeddingBackend()
    predictor = _RecordingProbabilityPredictor()
    loader = AtomEmbeddingModelLoader(lambda _model_name: backend)
    provider = _provider_with_runtime(LrClassifierRuntime(predictor))
    sentence = "Project Atlas implementation note. Ship only after review."
    text_inputs = [(0, SimpleNamespace(input_id="in_pipeline", source="composer", content=sentence))]

    outcome = evaluate_analyze_classifier(text_inputs, provider, loader)

    assert outcome.enabled is True
    assert outcome.has_candidates is True
    assert outcome.failure is None
    assert backend.seen_texts == [sentence]
    assert predictor.seen_vectors == [[1.0, 0.0]]


def test_evaluate_analyze_classifier_verifies_classifier_candidates_without_raw_leakage() -> None:
    raw_sentinel = "CLASSIFIER_VERIFIER_RAW_SENTINEL"
    verifier_model = _RecordingVerifierModel()
    loader = AtomEmbeddingModelLoader(lambda _model_name: _FakeEmbeddingBackend())
    provider = _provider_with_runtime(_CandidateRuntime())
    verifier_config = AnalyzeVerifierConfig(
        service=RobertaVerifierService(verifier_model),
        artifact=_verifier_artifact(),
    )
    text_inputs = [(0, SimpleNamespace(input_id="in_verify", source="composer", content=f"ordinary note {raw_sentinel}"))]

    outcome = evaluate_analyze_classifier(text_inputs, provider, loader, verifier_config=verifier_config)

    assert outcome.enabled is True
    assert outcome.has_candidates is True
    assert outcome.failure is None
    assert len(verifier_model.requests) == 1
    verifier_request = verifier_model.requests[0]
    assert verifier_request.input_id == "in_verify"
    assert len(verifier_request.candidates) == 1
    assert verifier_request.candidates[0].candidate_label == "secret_risk"
    assert outcome.verifier_summaries == [
        {
            "verification_count": 1,
            "accepted_count": 1,
            "status_counts": {"confirmed": 1, "rejected": 0, "uncertain": 0, "timeout": 0, "failed": 0},
            "labels": ["secret_risk"],
            "highest_confidence_bucket": "very_high",
            "verifier_model_versions": ["fake-roberta-v1"],
            "failure": None,
        }
    ]
    assert raw_sentinel not in json.dumps(outcome.verifier_summaries)
    assert raw_sentinel not in json.dumps(verifier_request.model_dump())


def test_evaluate_analyze_classifier_skips_verifier_when_classifier_has_no_candidates() -> None:
    verifier_model = _RecordingVerifierModel()
    loader = AtomEmbeddingModelLoader(lambda _model_name: _FakeEmbeddingBackend())
    provider = _provider_with_runtime(_NoCandidateRuntime())
    verifier_config = AnalyzeVerifierConfig(
        service=RobertaVerifierService(verifier_model),
        artifact=_verifier_artifact(),
    )
    text_inputs = [(0, SimpleNamespace(input_id="in_no_candidate", source="composer", content="ordinary note"))]

    outcome = evaluate_analyze_classifier(text_inputs, provider, loader, verifier_config=verifier_config)

    assert outcome.enabled is True
    assert outcome.has_candidates is False
    assert outcome.failure is None
    assert outcome.verifier_summaries == []
    assert verifier_model.requests == []


def test_evaluate_analyze_classifier_fails_closed_when_enabled_verifier_fails() -> None:
    loader = AtomEmbeddingModelLoader(lambda _model_name: _FakeEmbeddingBackend())
    provider = _provider_with_runtime(_CandidateRuntime())
    verifier_config = AnalyzeVerifierConfig(
        service=RobertaVerifierService(_FailingVerifierModel()),
        artifact=_verifier_artifact(),
    )
    text_inputs = [(0, SimpleNamespace(input_id="in_verifier_failure", source="composer", content="ordinary note"))]

    outcome = evaluate_analyze_classifier(text_inputs, provider, loader, verifier_config=verifier_config)

    assert outcome.enabled is True
    assert outcome.has_candidates is True
    assert outcome.failure is not None
    assert outcome.failure.code == "VERIFIER_MODEL_FAILED"
    assert "raw verifier failure sentinel" not in json.dumps(outcome.failure.model_dump())


def test_real_trained_lr_artifact_reaches_analyze_classifier_helper(tmp_path: Path) -> None:
    artifact_zip_path = _trained_artifact_zip_path_or_skip()
    artifact_root = tmp_path / "trained_classifier_artifact"
    with zipfile.ZipFile(artifact_zip_path) as archive:
        archive.extractall(artifact_root)

    manifest_path = artifact_root / "models" / "context_lr_roberta_best_v205_manifest.json"
    joblib_path = artifact_root / "models" / "context_with_patch_v205_deploy_candidate_classifier.joblib"
    bundle = build_classifier_service_from_manifest(manifest_path, artifact_root=artifact_root)
    vector_dimension = _trained_joblib_vector_dimension(joblib_path)
    loader = AtomEmbeddingModelLoader(
        lambda _model_name: _FixedDimensionEmbeddingBackend(
            vector_dimension,
            bundle.artifact.embedding_model_version,
        )
    )
    provider = ClassifierRuntimeProviderResult(bundle=bundle)
    text_inputs = [(0, SimpleNamespace(input_id="in_real_model", source="composer", content="ordinary implementation note"))]

    outcome = evaluate_analyze_classifier(text_inputs, provider, loader)

    assert bundle.artifact.artifact_id == "context_lr_roberta_best_v205"
    assert bundle.artifact.target_labels
    assert outcome.enabled is True
    assert outcome.failure is None
    assert isinstance(outcome.has_candidates, bool)


def test_evaluate_analyze_classifier_fails_closed_when_embedding_unavailable() -> None:
    provider = _provider_with_runtime(_CandidateRuntime())
    text_inputs = [(0, SimpleNamespace(input_id="in_1", source="composer", content="ordinary implementation note"))]

    outcome = evaluate_analyze_classifier(text_inputs, provider, embedding_loader=None)

    assert outcome.enabled is True
    assert outcome.has_candidates is False
    assert outcome.failure is not None
    assert outcome.failure.code == "EMBEDDING_MODEL_UNAVAILABLE"


def test_classifier_disabled_preserves_allow_without_classifier_call(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("disabled classifier should not run the Analyze classifier helper")

    monkeypatch.setattr(analyze_route, "evaluate_analyze_classifier", fail_if_called, raising=False)
    user = _user()
    client, fake_session = _client(user, rules=[], provider=_disabled_provider())

    response = client.post(
        "/prompts/analyze",
        json=_analyze_payload(_text_input("in_1", "plain implementation note")),
        headers=_bearer_header(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "Allow"
    assert body["allow_original_send"] is True
    assert body["requires_user_confirmation"] is False
    assert fake_session.commits == 1


def test_analyze_route_passes_verifier_config_to_classifier_helper(monkeypatch) -> None:
    seen = {}

    def capture_classifier(_text_inputs, _provider, _embedding_loader, *, verifier_config=None):
        seen["verifier_config"] = verifier_config
        return SimpleNamespace(enabled=True, has_candidates=False, failure=None, verifier_summaries=[])

    verifier_config = AnalyzeVerifierConfig(
        service=RobertaVerifierService(_RecordingVerifierModel()),
        artifact=_verifier_artifact(),
    )
    monkeypatch.setattr(analyze_route, "evaluate_analyze_classifier", capture_classifier, raising=False)
    user = _user()
    client, _fake_session = _client(user, rules=[], provider=_enabled_provider(), verifier_config=verifier_config)

    response = client.post(
        "/prompts/analyze",
        json=_analyze_payload(_text_input("in_1", "plain implementation note")),
        headers=_bearer_header(user.id),
    )

    assert response.status_code == 200
    assert seen["verifier_config"] is verifier_config
    assert "masked_prompt" not in response.json()


def test_classifier_candidate_escalates_allow_to_warn_without_raw_leakage(monkeypatch) -> None:
    sentinel = "CLASSIFIER_RAW_SECRET_SENTINEL"

    def candidate_outcome(*_args, **_kwargs):
        return SimpleNamespace(enabled=True, has_candidates=True, failure=None)

    monkeypatch.setattr(analyze_route, "evaluate_analyze_classifier", candidate_outcome, raising=False)
    user = _user()
    client, fake_session = _client(user, rules=[], provider=_enabled_provider())

    response = client.post(
        "/prompts/analyze",
        json=_analyze_payload(_text_input("in_1", f"ordinary note with {sentinel}")),
        headers=_bearer_header(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "Warn"
    assert body["allow_original_send"] is True
    assert body["requires_user_confirmation"] is True
    assert "masked_prompt" not in body
    assert body["detections"] == []
    assert sentinel not in json.dumps(body)
    assert sentinel not in _stored_payload(fake_session)


def test_classifier_failure_fails_closed_without_masked_prompt(monkeypatch) -> None:
    def failed_outcome(*_args, **_kwargs):
        return SimpleNamespace(
            enabled=True,
            has_candidates=False,
            failure=PipelineFailure(code="EMBEDDING_TIMEOUT", message="embedding timeout"),
        )

    monkeypatch.setattr(analyze_route, "evaluate_analyze_classifier", failed_outcome, raising=False)
    user = _user()
    client, _fake_session = _client(user, rules=[], provider=_enabled_provider())

    response = client.post(
        "/prompts/analyze",
        json=_analyze_payload(_text_input("in_1", "plain implementation note")),
        headers=_bearer_header(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "Block"
    assert body["allow_original_send"] is False
    assert body["requires_user_confirmation"] is False
    assert "masked_prompt" not in body


def test_classifier_candidate_does_not_downgrade_mask_or_block(monkeypatch) -> None:
    def candidate_outcome(*_args, **_kwargs):
        return SimpleNamespace(enabled=True, has_candidates=True, failure=None)

    monkeypatch.setattr(analyze_route, "evaluate_analyze_classifier", candidate_outcome, raising=False)
    user = _user()
    mask_rule = _filter_rule(keyword="Project Hermes", action="MASK")
    block_rule = _filter_rule(keyword="DoNotSend", action="BLOCK", placeholder="BLOCKED_CONTENT")
    client, _fake_session = _client(user, rules=[mask_rule, block_rule], provider=_enabled_provider())

    mask_response = client.post(
        "/prompts/analyze",
        json=_analyze_payload(
            _text_input("in_1", "Project Hermes launch note"),
            client_request_id="req_mask_with_classifier",
        ),
        headers=_bearer_header(user.id),
    )
    block_response = client.post(
        "/prompts/analyze",
        json=_analyze_payload(
            _text_input("in_2", "DoNotSend operational note"),
            client_request_id="req_block_with_classifier",
        ),
        headers=_bearer_header(user.id),
    )

    assert mask_response.status_code == 200
    assert mask_response.json()["action"] == "Mask"
    assert block_response.status_code == 200
    assert block_response.json()["action"] == "Block"
