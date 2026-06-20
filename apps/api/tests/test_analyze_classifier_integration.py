import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.atoms.models import PipelineFailure
from app.ml.classifier.factory import BuiltClassifierService, ClassifierRuntimeProviderResult
from app.ml.classifier.models import (
    ClassifierArtifactRef,
    SegmentClassificationCandidate,
    SegmentClassificationResult,
)
from app.ml.classifier.service import ClassifierService
from app.ml.embedding.loader import AtomEmbeddingModelLoader
from app.routes import analyze as analyze_route
from app.routes.auth import get_db_session
from app.services.analyze_classifier import evaluate_analyze_classifier

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


def _client(user=None, rules=None, provider=None) -> tuple[TestClient, _FakeSession]:
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


def _artifact() -> ClassifierArtifactRef:
    return ClassifierArtifactRef(
        artifact_id="fake-lr-artifact",
        manifest_version="1",
        runtime_version="lr-runtime-test",
        target_labels=["secret_risk"],
        candidate_threshold=0.8,
        embedding_model_version="fake-embedding-v1",
    )


def _provider_with_runtime(runtime) -> ClassifierRuntimeProviderResult:
    return ClassifierRuntimeProviderResult(
        bundle=BuiltClassifierService(
            service=ClassifierService(runtime),
            artifact=_artifact(),
        )
    )


def test_evaluate_analyze_classifier_uses_pipeline_and_reports_candidates() -> None:
    loader = AtomEmbeddingModelLoader(lambda _model_name: _FakeEmbeddingBackend())
    provider = _provider_with_runtime(_CandidateRuntime())
    text_inputs = [(0, SimpleNamespace(input_id="in_1", source="composer", content="ordinary implementation note"))]

    outcome = evaluate_analyze_classifier(text_inputs, provider, loader)

    assert outcome.enabled is True
    assert outcome.has_candidates is True
    assert outcome.failure is None


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
