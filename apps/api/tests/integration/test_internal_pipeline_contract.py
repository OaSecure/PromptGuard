import base64
from datetime import UTC, datetime

import pytest

from app.domain.policy import PolicyOrchestrator
from app.domain.types.policy import (
    PolicyDecisionRequest,
    PolicyInputEvidence,
    PolicyMlEvidence,
    PolicyRuleEvidence,
)
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.ml.classifier import SegmentClassificationCandidate, SegmentClassificationResult
from app.ml.verifier import (
    RobertaVerificationResult,
    RobertaVerifierService,
    VerifierArtifactRef,
    build_verification_request_from_classifier,
)
from app.parser.fakes import FakeParserPlanExecutor, FakeParserPlanResolver
from app.parser.models import (
    ParserBoundaryError,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    TempFileAccessContext,
    sanitized_failure,
)
from app.parser.runner import FileParserRunner


NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
RAW_SENTINEL = b"SYNTHETIC_INTERNAL_PIPELINE_CONTENT"


class StorageBackedResolver:
    def __init__(self, store, storage_context, now):
        self.store = store
        self.storage_context = storage_context
        self.now = now
        self.resolved = []

    def resolve(self, file_ref, access_context):
        if access_context.request_id != self.storage_context.request_id:
            raise ParserBoundaryError(sanitized_failure("TEMP_FILE_ACCESS_DENIED"))
        raw = self.store.resolve(file_ref, self.storage_context, self.now)
        self.resolved.append(raw)
        return ResolvedTemporaryFile(
            file_ref=file_ref,
            file_kind="plain_text",
            local_runtime_ref="in-memory-only",
        )


class RecordingVerifierModel:
    def __init__(self):
        self.requests = []

    def verify(self, request):
        self.requests.append(request)
        return RobertaVerificationResult(input_id=request.input_id)


def _parser_payload(file_ref, scope):
    return ParserWorkerPayload(
        input_id="file_input_1",
        request_id="request_1",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref=file_ref,
        file_kind="plain_text",
        access_context=TempFileAccessContext(
            authenticated_subject_id="subject_1",
            session_id="session_1",
            request_id="request_1",
            temp_scope_id=scope,
        ),
    )


def test_encrypted_resolution_parser_and_policy_contract_are_deterministic(tmp_path):
    store = EncryptedTemporaryFileStorage(
        tmp_path,
        base64.b64encode(b"K" * 32).decode(),
        900,
    )
    stored = store.store(
        RAW_SENTINEL,
        subject_id="subject_1",
        request_id="request_1",
        file_kind="plain_text",
        mime_hint="text/plain",
        extension_hint="txt",
        size_bucket="tiny",
        now=NOW,
    )
    from app.infrastructure.temp_storage import TempFileAccessContext as StorageContext

    storage_context = StorageContext("subject_1", "request_1", stored["temp_scope_id"])
    resolver = StorageBackedResolver(store, storage_context, NOW)
    runner = FileParserRunner(resolver, FakeParserPlanResolver(), FakeParserPlanExecutor())

    result = runner.run(_parser_payload(stored["file_ref"], stored["temp_scope_id"]))
    decision = PolicyOrchestrator().decide(
        PolicyDecisionRequest(
            request_id="request_1",
            input_ids=["file_input_1"],
            inputs=[PolicyInputEvidence(input_id="file_input_1", content_scanned=result.parser_status == "parsed")],
        )
    )

    assert result.parser_status == "parsed"
    assert resolver.resolved == [RAW_SENTINEL]
    assert decision.action == "allow"
    assert RAW_SENTINEL not in b"".join(path.read_bytes() for path in tmp_path.iterdir())


@pytest.mark.parametrize(
    ("owner", "failure_code"),
    [("resolver", "TEMP_FILE_RESOLVE_FAILED"), ("plan", "PARSER_DISABLED"), ("executor", "PARSER_WORKER_FAILED")],
)
def test_parser_boundary_failures_project_to_warn_policy(owner, failure_code):
    from app.parser.fakes import FakeTemporaryFileResolver

    runner = FileParserRunner(
        FakeTemporaryFileResolver(failure_code=failure_code if owner == "resolver" else None),
        FakeParserPlanResolver(failure_code=failure_code if owner == "plan" else None),
        FakeParserPlanExecutor(failure_code=failure_code if owner == "executor" else None),
    )
    result = runner.run(_parser_payload("opaque-ref-1", "scope-1"))
    decision = PolicyOrchestrator().decide(
        PolicyDecisionRequest(
            request_id="request_1",
            input_ids=["file_input_1"],
            evidence_codes=["PARSER_OR_OCR_FAILED"],
            inputs=[PolicyInputEvidence(input_id="file_input_1", content_scanned=False)],
        )
    )

    assert result.failure.code == failure_code
    assert decision.action == "warn"
    assert decision.reason_code == "PARSER_OR_OCR_FAILED"


def test_candidate_only_verifier_and_policy_never_downgrade_stronger_rule():
    artifact = VerifierArtifactRef(
        artifact_id="fake-verifier",
        model_version="fake-model",
        runtime_version="fake-runtime",
    )
    candidate = SegmentClassificationCandidate(
        segment_id="segment_1",
        label="secret",
        score=0.91,
        threshold=0.8,
        artifact_id="fake-classifier",
        runtime_version="fake-runtime",
    )
    model = RecordingVerifierModel()
    service = RobertaVerifierService(model)

    empty_request = build_verification_request_from_classifier(
        input_id="input_1",
        classification=SegmentClassificationResult(input_id="input_1"),
        artifact=artifact,
    )
    service.verify(empty_request)
    candidate_request = build_verification_request_from_classifier(
        input_id="input_1",
        classification=SegmentClassificationResult(input_id="input_1", candidates=[candidate]),
        artifact=artifact,
    )
    service.verify(candidate_request)

    decision = PolicyOrchestrator().decide(
        PolicyDecisionRequest(
            request_id="request_1",
            input_ids=["input_1"],
            inputs=[PolicyInputEvidence(input_id="input_1", content_scanned=True)],
            rules=[PolicyRuleEvidence(action="mask", severity="high", reason_code="LEXICAL_DETERMINISTIC_SECRET_SIGNAL")],
            ml=PolicyMlEvidence(classifier_enabled=True, classifier_has_candidates=True),
        )
    )

    assert len(model.requests) == 1
    assert [item.candidate_label for item in model.requests[0].candidates] == ["secret"]
    assert decision.action == "mask"
