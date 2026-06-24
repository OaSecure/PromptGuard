from dataclasses import dataclass, field
from typing import Any

from app.atoms.builder import build_atoms
from app.atoms.models import AtomBuildRequest, ParsedBlock, ParsedDocument, PipelineFailure
from app.mapping import (
    LexicalSignal as MappingLexicalSignal,
    SignalMappingPolicy,
    SignalMappingRequest,
    map_signals_to_segments,
)
from app.ml.classifier.factory import ClassifierRuntimeProviderResult
from app.ml.classifier.metadata import project_classification_signal_summary
from app.ml.classifier.models import SegmentClassificationRequest
from app.ml.embedding.loader import AtomEmbeddingModelLoader
from app.ml.embedding.models import AtomEmbeddingRequest
from app.ml.embedding.worker import embed_atoms
from app.ml.segment_embedding.builder import build_segment_embeddings
from app.ml.segment_embedding.models import SegmentEmbeddingBuildRequest, SegmentEmbeddingPolicy
from app.ml.verifier import (
    RobertaVerifierService,
    VerifierArtifactRef,
    build_verification_request_from_classifier,
    project_verification_signal_summary,
)
from app.normalization import NormalizerRequest, normalize_document
from app.runtime.ml_inference_queue import MlInferenceJob, MlInferenceQueue
from app.scanner import (
    LexicalRule,
    LexicalScanRequest,
    LexicalSignal as ScannerLexicalSignal,
    scan_lexical_signals,
)
from app.segmenter.builder import build_segments
from app.segmenter.models import SegmentBuildRequest, SegmentPolicy

CLASSIFIER_RUNTIME_DISABLED = "CLASSIFIER_RUNTIME_DISABLED"
ANALYZE_CLASSIFIER_FAILED = "ANALYZE_CLASSIFIER_FAILED"
NORMALIZATION_FAILED = "NORMALIZATION_FAILED"
LEXICAL_SCAN_FAILED = "LEXICAL_SCAN_FAILED"
DEFAULT_ANALYZE_ML_INFERENCE_TIMEOUT_MS = 3000

_MAPPING_SIGNAL_TYPES = {
    "pii_span",
    "secret_span",
    "secret_fingerprint",
    "token_candidate",
    "protected_target_hit",
    "custom_regex_hit",
    "sensitive_value_pattern_hit",
    "context_trigger_hit",
}


@dataclass(frozen=True)
class AnalyzeClassifierOutcome:
    enabled: bool
    has_candidates: bool = False
    failure: PipelineFailure | None = None
    verifier_summaries: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AnalyzeVerifierConfig:
    service: RobertaVerifierService
    artifact: VerifierArtifactRef
    timeout_ms: int = 3000


def evaluate_analyze_classifier(
    text_inputs: list[tuple[int, Any]],
    provider_result: ClassifierRuntimeProviderResult,
    embedding_loader: AtomEmbeddingModelLoader | None,
    *,
    verifier_config: AnalyzeVerifierConfig | None = None,
    lexical_rules: list[LexicalRule] | None = None,
    inference_queue: MlInferenceQueue | None = None,
    inference_timeout_ms: int = DEFAULT_ANALYZE_ML_INFERENCE_TIMEOUT_MS,
) -> AnalyzeClassifierOutcome:
    if _is_disabled(provider_result):
        return AnalyzeClassifierOutcome(enabled=False)
    if not provider_result.available or provider_result.bundle is None:
        return AnalyzeClassifierOutcome(
            enabled=True,
            failure=provider_result.failure or _failure(ANALYZE_CLASSIFIER_FAILED),
        )

    has_candidates = False
    verifier_summaries: list[dict[str, Any]] = []
    for _index, item in text_inputs:
        input_id = getattr(item, "input_id", "")
        content = getattr(item, "content", None)
        if not isinstance(content, str) or not content.strip():
            continue

        document = _document_for_input(item)
        normalized_document = normalize_document(NormalizerRequest(document=document))
        if normalized_document.failures:
            return AnalyzeClassifierOutcome(enabled=True, failure=_failure(NORMALIZATION_FAILED))

        scan_result = scan_lexical_signals(
            LexicalScanRequest(
                normalized_document=normalized_document,
                rules=lexical_rules or [],
            )
        )
        if scan_result.failures:
            return AnalyzeClassifierOutcome(enabled=True, failure=_failure(LEXICAL_SCAN_FAILED))

        atom_result = build_atoms(AtomBuildRequest(document=document))
        if atom_result.failures:
            return AnalyzeClassifierOutcome(enabled=True, failure=atom_result.failures[0])
        if not atom_result.atoms:
            continue

        embedding_result = embed_atoms(
            AtomEmbeddingRequest(input_id=input_id, atoms=atom_result.atoms),
            loader=embedding_loader,
        )
        if embedding_result.failure is not None:
            return AnalyzeClassifierOutcome(enabled=True, failure=embedding_result.failure)

        segment_result = build_segments(
            SegmentBuildRequest(
                input_id=input_id,
                atoms=atom_result.atoms,
                atom_embeddings=embedding_result.embeddings,
                segment_policy=SegmentPolicy(),
            )
        )
        if segment_result.failure is not None:
            return AnalyzeClassifierOutcome(enabled=True, failure=segment_result.failure)

        mapping_result = map_signals_to_segments(
            SignalMappingRequest(
                input_id=input_id,
                segments=segment_result.segments,
                atoms=atom_result.atoms,
                lexical_signals=[_mapping_signal_from_scanner(signal) for signal in scan_result.signals],
                mapping_policy=SignalMappingPolicy(),
            )
        )
        if mapping_result.failure is not None:
            return AnalyzeClassifierOutcome(enabled=True, failure=mapping_result.failure)

        segment_embedding_result = build_segment_embeddings(
            SegmentEmbeddingBuildRequest(
                input_id=input_id,
                segments=segment_result.segments,
                atom_embeddings=embedding_result.embeddings,
                embedding_model_version=embedding_result.embedding_model_version,
                policy=SegmentEmbeddingPolicy(),
            )
        )
        if segment_embedding_result.failure is not None:
            return AnalyzeClassifierOutcome(enabled=True, failure=segment_embedding_result.failure)

        classification_request = SegmentClassificationRequest(
            input_id=input_id,
            segment_embeddings=segment_embedding_result.segment_embeddings,
            artifact=provider_result.bundle.artifact,
        )
        classification_result = _run_classifier_inference(
            input_id,
            classification_request,
            provider_result,
            inference_queue,
            inference_timeout_ms,
        )
        if isinstance(classification_result, PipelineFailure):
            return AnalyzeClassifierOutcome(enabled=True, failure=classification_result)
        if classification_result.failure is not None:
            return AnalyzeClassifierOutcome(enabled=True, failure=classification_result.failure)

        summary = project_classification_signal_summary(classification_result)
        has_candidates = has_candidates or bool(summary["has_candidates"])
        if summary["has_candidates"] and verifier_config is not None:
            segment_text_by_id = {segment.segment_id: segment.text for segment in segment_result.segments}
            verification_request = build_verification_request_from_classifier(
                input_id=input_id,
                classification=classification_result,
                artifact=verifier_config.artifact,
                timeout_ms=verifier_config.timeout_ms,
                candidate_text_by_segment_id={
                    candidate.segment_id: segment_text_by_id.get(candidate.segment_id, "")
                    for candidate in classification_result.candidates
                },
            )
            verification_result = _run_verifier_inference(
                input_id,
                verification_request,
                verifier_config,
                inference_queue,
                inference_timeout_ms,
            )
            if isinstance(verification_result, PipelineFailure):
                return AnalyzeClassifierOutcome(
                    enabled=True,
                    has_candidates=True,
                    failure=verification_result,
                    verifier_summaries=verifier_summaries,
                )
            if verification_result.failure is not None:
                return AnalyzeClassifierOutcome(
                    enabled=True,
                    has_candidates=True,
                    failure=verification_result.failure,
                    verifier_summaries=verifier_summaries,
                )
            verifier_summaries.append(project_verification_signal_summary(verification_result))

    return AnalyzeClassifierOutcome(enabled=True, has_candidates=has_candidates, verifier_summaries=verifier_summaries)


def _is_disabled(provider_result: ClassifierRuntimeProviderResult) -> bool:
    return provider_result.failure is not None and provider_result.failure.code == CLASSIFIER_RUNTIME_DISABLED


def _run_classifier_inference(
    input_id: str,
    request: SegmentClassificationRequest,
    provider_result: ClassifierRuntimeProviderResult,
    inference_queue: MlInferenceQueue | None,
    timeout_ms: int,
):
    if inference_queue is None:
        return provider_result.bundle.service.classify(request)
    result = inference_queue.execute(
        MlInferenceJob(
            job_id=f"{input_id}:classifier",
            request_id=input_id,
            task_type="classifier",
            metadata={
                "model": "classifier",
                "segment_count": len(request.segment_embeddings),
                "timeout_ms": timeout_ms,
            },
        ),
        timeout_ms=timeout_ms,
        operation=lambda: provider_result.bundle.service.classify(request),
    )
    if result.status != "succeeded":
        return _failure(result.failure_code or ANALYZE_CLASSIFIER_FAILED)
    return result.value


def _run_verifier_inference(
    input_id: str,
    request,
    verifier_config: AnalyzeVerifierConfig,
    inference_queue: MlInferenceQueue | None,
    timeout_ms: int,
):
    if inference_queue is None:
        return verifier_config.service.verify(request)
    result = inference_queue.execute(
        MlInferenceJob(
            job_id=f"{input_id}:verifier",
            request_id=input_id,
            task_type="verifier",
            metadata={
                "model": "verifier",
                "candidate_count": len(request.candidates),
                "timeout_ms": timeout_ms,
            },
        ),
        timeout_ms=timeout_ms,
        operation=lambda: verifier_config.service.verify(request),
    )
    if result.status != "succeeded":
        return _failure(result.failure_code or ANALYZE_CLASSIFIER_FAILED)
    return result.value


def _document_for_input(item: object) -> ParsedDocument:
    input_id = getattr(item, "input_id", "")
    source = getattr(item, "source", "text")
    return ParsedDocument(
        input_id=input_id,
        blocks=[
            ParsedBlock(
                block_id=f"{input_id}:text",
                input_id=input_id,
                text=getattr(item, "content"),
                source_type=source,
            )
        ],
        parser_id="analyze-input-v1",
    )


def _mapping_signal_from_scanner(signal: ScannerLexicalSignal) -> MappingLexicalSignal:
    return MappingLexicalSignal(
        signal_id=signal.signal_id,
        input_id=signal.input_id,
        block_id=signal.block_id,
        signal_type=_mapping_signal_type(signal.signal_type),
        pattern_id=signal.pattern_id,
        match_basis="keyword" if signal.match_basis == "keyword" else "deterministic_regex",
        normalized_range=signal.normalized_range,
        original_range=signal.original_range,
        severity_hint=signal.severity_hint or "low",
        deterministic=signal.deterministic,
        value_fingerprint=signal.value_fingerprint,
        metadata=dict(signal.metadata),
    )


def _mapping_signal_type(signal_type: str) -> str:
    if signal_type in _MAPPING_SIGNAL_TYPES:
        return signal_type
    return "custom_regex_hit"


def _failure(code: str) -> PipelineFailure:
    return PipelineFailure(code=code, message=code, metadata={"failure_code": code})
