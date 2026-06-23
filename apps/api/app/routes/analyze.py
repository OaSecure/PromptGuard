# -*- coding: utf-8 -*-
import json
import re
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from types import SimpleNamespace
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.analyze.parser_payload import build_file_reference_parser_worker_payload
from app.application.analyze.policy_adapter import build_policy_request, get_policy_orchestrator, to_legacy_action
from app.atoms.models import ParsedDocument
from app.core.config import Settings, get_settings
from app.core.tokens import utc_now
from app.interfaces.http.analyze_request import LegacyAnalyzeRequest, adapt_legacy_analyze_request
from app.interfaces.http.response_adapter import AnalyzeInputResult, AnalyzeResponse, build_analyze_response
from app.masking.placeholder import apply_placeholders
from app.ml.classifier.factory import ClassifierRuntimeProviderResult, build_classifier_service_from_settings
from app.ml.embedding import create_qwen3_backend
from app.ml.embedding.loader import AtomEmbeddingModelLoader
from app.ml.gpu_capacity import GpuWorkerCapacityPolicy, TorchCudaGpuCapacityProbe, resolve_gpu_worker_capacity
from app.ml.verifier import VerifierServiceBuildError, build_verifier_service_from_manifest
from app.parser.models import FileParserResult, TempFileAccessContext
from app.runtime.ml_inference_queue import MlInferenceQueue
from app.runtime.parser_worker import ParserWorkerPool
from app.models.auth import User
from app.models.filters import FilterRule
from app.events.writer import SqlAlchemyEventWriter, load_idempotency_event_id as load_idempotency_key
from app.privacy import serialize_event_write
from app.ports.policy import PolicyOrchestratorPort
from app.routes.auth import get_db_session, require_active_user
from app.services.analyze_classifier import AnalyzeClassifierOutcome, AnalyzeVerifierConfig, evaluate_analyze_classifier
from app.services.filter_rules import (
    RuleMatch,
    detections_for_masking,
    evaluate_filter_rules,
    load_active_filter_rules,
    score_for_matches,
)

router = APIRouter(prefix="/prompts", tags=["prompts"])

MAX_ANALYZE_REQUEST_BYTES = 2_097_152
MAX_COMPOSER_TEXT_BYTES = 262_144
MAX_CONVERTED_PASTE_TEXT_BYTES = 1_048_576
IDEMPOTENCY_TTL = timedelta(hours=24)
SAFE_CONTEXT_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
SAFE_CONTEXT_DOMAIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")
SAFE_INPUT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SAFE_CLIENT_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SAFE_FILTER_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SECRET_LIKE_ID_RE = re.compile(
    r"(?:gh[pousr]_|sk-[A-Za-z0-9]|xox[baprs]-|AKIA[0-9A-Z]|postgres://|mysql://|bearer|private[_-]?key)",
    re.IGNORECASE,
)

ACTION_MASK = "MASK"
ACTION_BLOCK = "BLOCK"

TEXT_SOURCES = ("composer", "converted_paste")
CONTENT_UNAVAILABLE_REASONS = ("oversized", "unsupported", "metadata_only", "unavailable")
LIMIT_EXCEEDED_CODES = (
    "MAX_ANALYZE_REQUEST_BYTES",
    "MAX_COMPOSER_TEXT_BYTES",
    "MAX_CONVERTED_PASTE_TEXT_BYTES",
)
TEXT_SOURCE_LIMITS = {
    "composer": MAX_COMPOSER_TEXT_BYTES,
    "converted_paste": MAX_CONVERTED_PASTE_TEXT_BYTES,
}
FORBIDDEN_METADATA_KEYS = {"name", "filename", "file_name", "original_filename", "path", "url"}


class AnalyzeRoute(APIRoute):
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            body = await request.body()
            if len(body) > MAX_ANALYZE_REQUEST_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Analyze request body is too large"},
                )
            return await original_route_handler(request)

        return custom_route_handler


router.route_class = AnalyzeRoute


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=1, max_length=128, pattern=SAFE_CLIENT_REQUEST_ID_RE.pattern)
    filter_config_revision: str = Field(min_length=1, max_length=80, pattern=SAFE_FILTER_REVISION_RE.pattern)
    context: "AnalyzeContext"
    inputs: list["AnalyzeInput"] = Field(min_length=1, max_length=20)

    @field_validator("client_request_id", "filter_config_revision")
    @classmethod
    def id_fields_must_not_look_like_secrets(cls, value: str) -> str:
        if SECRET_LIKE_ID_RE.search(value):
            raise ValueError("id field must not contain secret-like values")
        return value

    @field_validator("inputs")
    @classmethod
    def input_ids_must_be_unique(cls, value: list["AnalyzeInput"]) -> list["AnalyzeInput"]:
        input_ids = [item.input_id for item in value]
        if len(set(input_ids)) != len(input_ids):
            raise ValueError("input_id values must be unique")
        return value


class AnalyzeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_service: str = Field(min_length=1, max_length=32, pattern=SAFE_CONTEXT_LABEL_RE.pattern)
    ai_service_domain: str = Field(min_length=1, max_length=255, pattern=SAFE_CONTEXT_DOMAIN_RE.pattern)
    page_url_origin: str = Field(min_length=1, max_length=255, pattern=r"^https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?$")
    extension_version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
    browser: str = Field(min_length=1, max_length=32, pattern=SAFE_CONTEXT_LABEL_RE.pattern)
    locale: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")


class AnalyzeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str = Field(min_length=1, max_length=80, pattern=SAFE_INPUT_ID_RE.pattern)
    kind: Literal["text", "attachment_metadata", "unsupported_attachment"]
    source: Literal["composer", "converted_paste", "attachment_chip"]
    size_bytes: int = Field(ge=0, le=2_147_483_647)
    content_included: bool
    content: str | None = Field(default=None, max_length=1_048_576)
    metadata: dict[str, Any] | None = None
    content_unavailable_reason: Literal["oversized", "unsupported", "metadata_only", "unavailable"] | None = None
    limit_exceeded: Literal[
        "MAX_ANALYZE_REQUEST_BYTES",
        "MAX_COMPOSER_TEXT_BYTES",
        "MAX_CONVERTED_PASTE_TEXT_BYTES",
    ] | None = None

    @field_validator("input_id")
    @classmethod
    def input_id_must_not_look_like_secret(cls, value: str) -> str:
        if SECRET_LIKE_ID_RE.search(value):
            raise ValueError("input_id must not contain secret-like values")
        return value

    @model_validator(mode="after")
    def validate_input_contract(self) -> "AnalyzeInput":
        if self.kind == "text":
            if self.source not in TEXT_SOURCES:
                raise ValueError("text input source must be composer or converted_paste")
            if self.content_included:
                if self.content is None or not self.content.strip():
                    raise ValueError("included text input must include non-blank content")
                content_size = len(self.content.encode("utf-8"))
                if content_size != self.size_bytes:
                    raise ValueError("size_bytes must equal UTF-8 content byte length")
                if content_size > TEXT_SOURCE_LIMITS[self.source]:
                    raise ValueError("included text input exceeds source byte limit")
                if self.content_unavailable_reason is not None or self.limit_exceeded is not None:
                    raise ValueError("included text input must not include unavailable metadata")
            else:
                if self.content is not None:
                    raise ValueError("content_unavailable text input must not include content")
                if self.content_unavailable_reason is None:
                    raise ValueError("content_unavailable text input must include a reason")
                if self.limit_exceeded is None and self.content_unavailable_reason == "oversized":
                    raise ValueError("oversized text input must include limit_exceeded")
        elif self.kind == "attachment_metadata":
            if self.source != "attachment_chip":
                raise ValueError("attachment_metadata source must be attachment_chip")
            if self.content_included:
                raise ValueError("attachment_metadata content_included must be false")
            if self.content is not None:
                raise ValueError("attachment_metadata must not include content")
            if self.metadata is None:
                raise ValueError("attachment_metadata must include metadata")
            validate_safe_attachment_metadata(self.metadata)
        else:
            if self.source != "attachment_chip":
                raise ValueError("unsupported_attachment source must be attachment_chip")
            if self.content_included:
                raise ValueError("unsupported_attachment content_included must be false")
            if self.content is not None:
                raise ValueError("unsupported_attachment must not include content")
            if self.content_unavailable_reason is None:
                raise ValueError("unsupported_attachment must include a reason")
        return self


def validate_safe_attachment_metadata(metadata: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("attachment metadata must be JSON serializable") from exc

    if len(encoded) > 2_048:
        raise ValueError("attachment metadata is too large")

    for key in unsafe_metadata_keys(metadata):
        if key.casefold() in FORBIDDEN_METADATA_KEYS:
            raise ValueError("attachment metadata must not include original filename, path, or URL")


def unsafe_metadata_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        keys = list(value.keys())
        for nested_value in value.values():
            keys.extend(unsafe_metadata_keys(nested_value))
        return [key for key in keys if isinstance(key, str)]
    if isinstance(value, list):
        keys: list[str] = []
        for item in value:
            keys.extend(unsafe_metadata_keys(item))
        return keys
    return []


def risk_level_for_score(score: int) -> Literal["low", "medium", "high", "critical"]:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def included_text_inputs(payload: AnalyzeRequest) -> list[tuple[int, AnalyzeInput]]:
    return [
        (index, item)
        for index, item in enumerate(payload.inputs)
        if item.kind == "text" and item.content_included and item.content is not None
    ]


def matched_text_inputs(text_inputs: list[tuple[int, AnalyzeInput]], rules: list[FilterRule]) -> list[tuple[int, AnalyzeInput, list[RuleMatch]]]:
    return [
        (index, item, matches)
        for index, item in text_inputs
        if (matches := evaluate_filter_rules(item.content or "", rules))
    ]


def first_composer_input(text_inputs: list[tuple[int, AnalyzeInput]]) -> tuple[int, AnalyzeInput] | None:
    for index, item in text_inputs:
        if item.source == "composer":
            return index, item
    return None


def unavailable_inputs(payload: AnalyzeRequest) -> list[tuple[int, AnalyzeInput]]:
    return [(index, item) for index, item in enumerate(payload.inputs) if not item.content_included]


def input_results_for_payload(
    payload: AnalyzeRequest,
    detection_input_indexes: set[int],
    parser_results: dict[int, FileParserResult] | None = None,
) -> list[AnalyzeInputResult]:
    results: list[AnalyzeInputResult] = []
    parser_results = parser_results or {}
    for index, item in enumerate(payload.inputs):
        content_scanned, decision_basis = _input_scan_result(
            item,
            index=index,
            detection_input_indexes=detection_input_indexes,
            parser_result=parser_results.get(index),
        )

        results.append(
            AnalyzeInputResult(
                input_id=item.input_id,
                input_index=index,
                kind=item.kind,
                source=item.source,
                content_included=item.content_included,
                content_scanned=content_scanned,
                decision_basis=decision_basis,
                content_unavailable_reason=item.content_unavailable_reason,
                limit_exceeded=item.limit_exceeded,
            )
        )
    return results


def _input_scan_result(
    item: Any,
    *,
    index: int,
    detection_input_indexes: set[int],
    parser_result: FileParserResult | None,
) -> tuple[bool, str]:
    if parser_result is not None and parser_result.parser_status == "parsed" and parser_result.document is not None:
        return True, "detection" if index in detection_input_indexes else "no_detection"
    if item.content_included:
        return item.kind == "text", "detection" if index in detection_input_indexes else "no_detection"
    if item.kind == "attachment_metadata":
        return False, "metadata_only"
    return False, "content_unavailable"


def score_for_final_action(score: int, action: str) -> int:
    if action == ACTION_BLOCK:
        return max(score, 95)
    return score


def duplicate_request_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "DUPLICATE_REQUEST_RETRY_REQUIRED",
            "message": "Duplicate Analyze request cannot be safely replayed. Retry with a new client_request_id.",
        },
    )


def is_idempotency_conflict(error: IntegrityError) -> bool:
    message = str(error).casefold()
    return "idempotency_keys" in message or "pk_idempotency_keys" in message


@lru_cache(maxsize=8)
def _cached_classifier_runtime_provider(
    classifier_runtime_enabled: bool,
    classifier_manifest_path: str,
) -> ClassifierRuntimeProviderResult:
    settings = Settings(
        PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=classifier_runtime_enabled,
        PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=classifier_manifest_path,
    )
    return build_classifier_service_from_settings(settings)


def get_classifier_runtime_provider(settings: Settings = Depends(get_settings)) -> ClassifierRuntimeProviderResult:
    return _cached_classifier_runtime_provider(
        settings.classifier_runtime_enabled,
        settings.classifier_manifest_path,
    )


def get_atom_embedding_loader(settings: Settings = Depends(get_settings)) -> AtomEmbeddingModelLoader | None:
    if not settings.classifier_runtime_enabled:
        return None
    return AtomEmbeddingModelLoader(create_qwen3_backend)


def _build_analyze_verifier_config_from_settings(
    settings: Settings,
    *,
    builder=build_verifier_service_from_manifest,
) -> AnalyzeVerifierConfig | None:
    if not settings.verifier_runtime_enabled:
        return None
    manifest_path = settings.verifier_manifest_path_value()
    if manifest_path is None:
        return None
    try:
        bundle = builder(manifest_path)
    except VerifierServiceBuildError:
        return None
    return AnalyzeVerifierConfig(service=bundle.service, artifact=bundle.artifact)


@lru_cache(maxsize=8)
def _cached_analyze_verifier_config(
    verifier_runtime_enabled: bool,
    verifier_manifest_path: str,
) -> AnalyzeVerifierConfig | None:
    settings = Settings(
        PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=verifier_runtime_enabled,
        PROMPTGUARD_VERIFIER_MANIFEST_PATH=verifier_manifest_path,
    )
    return _build_analyze_verifier_config_from_settings(settings)


def get_analyze_verifier_config(settings: Settings = Depends(get_settings)) -> AnalyzeVerifierConfig | None:
    return _cached_analyze_verifier_config(
        settings.verifier_runtime_enabled,
        settings.verifier_manifest_path,
    )


@lru_cache(maxsize=8)
def _cached_ml_inference_queue(
    enabled: bool,
    max_workers: int,
    max_queue_size: int,
) -> MlInferenceQueue | None:
    if not enabled:
        return None
    return MlInferenceQueue(max_workers=max_workers, max_queue_size=max_queue_size)


def get_ml_inference_queue(settings: Settings = Depends(get_settings)) -> MlInferenceQueue | None:
    return _cached_ml_inference_queue(
        settings.ml_inference_queue_enabled,
        _resolve_ml_inference_max_workers(settings),
        settings.ml_inference_queue_max_queue_size,
    )


def _resolve_ml_inference_max_workers(settings: Settings) -> int:
    decision = resolve_gpu_worker_capacity(
        GpuWorkerCapacityPolicy(
            enabled=settings.ml_inference_gpu_capacity_enabled,
            configured_workers=settings.ml_inference_queue_max_workers,
            max_workers=settings.ml_inference_queue_max_workers,
            reserved_memory_mb=settings.ml_inference_gpu_reserved_memory_mb,
            memory_per_worker_mb=settings.ml_inference_gpu_memory_per_worker_mb,
        ),
        probe=TorchCudaGpuCapacityProbe(),
    )
    return decision.worker_count


def get_parser_worker_pool() -> ParserWorkerPool | None:
    return None


def parser_results_for_payload(
    payload: LegacyAnalyzeRequest,
    *,
    current_user: User,
    parser_worker_pool: ParserWorkerPool | None,
    timeout_ms: int,
) -> dict[int, FileParserResult]:
    if parser_worker_pool is None:
        return {}
    results: dict[int, FileParserResult] = {}
    for index, item in enumerate(payload.inputs):
        if item.kind != "file_reference":
            continue
        access_context = TempFileAccessContext(
            authenticated_subject_id=str(current_user.id),
            session_id=str(current_user.id),
            request_id=payload.client_request_id,
            temp_scope_id=item.temp_scope_id,
        )
        parser_payload = build_file_reference_parser_worker_payload(
            payload.client_request_id,
            item,
            access_context=access_context,
        )
        results[index] = parser_worker_pool.execute(parser_payload, timeout_ms=timeout_ms)
    return results


def parsed_file_matches(
    payload: LegacyAnalyzeRequest,
    parser_results: dict[int, FileParserResult],
    rules: list[FilterRule],
) -> list[tuple[int, Any, list[RuleMatch]]]:
    matched: list[tuple[int, Any, list[RuleMatch]]] = []
    for index, result in parser_results.items():
        document = result.document
        if result.parser_status != "parsed" or document is None:
            continue
        text = _runtime_text_from_document(document)
        if not text:
            continue
        item = payload.inputs[index]
        matches = evaluate_filter_rules(text, rules)
        if matches:
            matched.append((index, _parsed_file_match_item(item, text), matches))
    return matched


def _runtime_text_from_document(document: ParsedDocument) -> str:
    return "\n".join(block.text for block in document.blocks if block.text)


def _parsed_file_match_item(item: Any, content: str) -> SimpleNamespace:
    return SimpleNamespace(
        input_id=item.input_id,
        kind=item.kind,
        source=item.source,
        content=content,
        content_included=False,
    )


@router.post("/analyze", response_model=AnalyzeResponse, response_model_exclude_none=True)
async def analyze_prompt(
    payload: LegacyAnalyzeRequest,
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db_session),
    classifier_provider: ClassifierRuntimeProviderResult = Depends(get_classifier_runtime_provider),
    embedding_loader: AtomEmbeddingModelLoader | None = Depends(get_atom_embedding_loader),
    verifier_config: AnalyzeVerifierConfig | None = Depends(get_analyze_verifier_config),
    inference_queue: MlInferenceQueue | None = Depends(get_ml_inference_queue),
    parser_worker_pool: ParserWorkerPool | None = Depends(get_parser_worker_pool),
    settings: Settings = Depends(get_settings),
    policy_orchestrator: PolicyOrchestratorPort = Depends(get_policy_orchestrator),
) -> AnalyzeResponse:
    adapted_request = adapt_legacy_analyze_request(payload, current_user.login_id)
    payload = adapted_request.legacy_view
    request_id = payload.client_request_id
    event_id = uuid.uuid4()
    checked_at = utc_now()
    existing_idempotency_key = await load_idempotency_key(session, current_user.login_id, payload.client_request_id)
    if existing_idempotency_key is not None:
        raise duplicate_request_error()

    rules = await load_active_filter_rules(session)
    text_inputs = included_text_inputs(payload)
    matched_inputs = matched_text_inputs(text_inputs, rules)
    parser_results = parser_results_for_payload(
        payload,
        current_user=current_user,
        parser_worker_pool=parser_worker_pool,
        timeout_ms=settings.ml_inference_queue_timeout_ms,
    )
    matched_inputs.extend(parsed_file_matches(payload, parser_results, rules))
    matches = [match for _index, _item, item_matches in matched_inputs for match in item_matches]
    detection_target = first_composer_input([(index, item) for index, item, item_matches in matched_inputs if item_matches])
    risk_score = score_for_matches(matches)
    classifier_outcome = (
        AnalyzeClassifierOutcome(enabled=False)
        if classifier_provider.failure is not None and classifier_provider.failure.code == "CLASSIFIER_RUNTIME_DISABLED"
        else evaluate_analyze_classifier(
            text_inputs,
            classifier_provider,
            embedding_loader,
            verifier_config=verifier_config,
            inference_queue=inference_queue,
            inference_timeout_ms=settings.ml_inference_queue_timeout_ms,
        )
    )
    detection_input_indexes = {index for index, _item, item_matches in matched_inputs if item_matches}
    input_results = input_results_for_payload(payload, detection_input_indexes, parser_results)
    policy_request = build_policy_request(request_id, payload.inputs, matched_inputs, classifier_outcome, input_results=input_results)
    action = to_legacy_action(policy_orchestrator.decide(policy_request).action)
    risk_score = score_for_final_action(risk_score, action)
    risk_level = risk_level_for_score(risk_score)
    masking_matches = []
    if detection_target is not None:
        masking_matches = next(
            (item_matches for index, _item, item_matches in matched_inputs if index == detection_target[0]),
            [],
        )
    masking_detections = detections_for_masking(masking_matches)
    composer_text = detection_target[1].content if detection_target is not None else None
    masked = apply_placeholders(composer_text, masking_detections) if action == ACTION_MASK and masking_detections and composer_text else None

    event_projection = serialize_event_write(
        event_id=event_id, user_id=current_user.id, login_id=current_user.login_id,
        payload=payload, action=action, risk_score=risk_score, risk_level=risk_level,
        input_results=input_results, matched_inputs=matched_inputs,
        idempotency_expires_at=checked_at + IDEMPOTENCY_TTL,
    )
    current_user.last_event_at = checked_at
    try:
        await SqlAlchemyEventWriter(session).write(event_projection)
    except IntegrityError as exc:
        if is_idempotency_conflict(exc):
            raise duplicate_request_error() from exc
        raise

    return build_analyze_response(
        event_id=event_id, request_id=request_id, checked_at=checked_at, action=action,
        risk_score=risk_score, risk_level=risk_level, payload=payload,
        matched_inputs=matched_inputs, input_results=input_results,
        masked_prompt=masked.text if masked is not None else None,
        masked_source=detection_target[1].source if detection_target is not None else None,
    )
