from dataclasses import dataclass, field
from typing import Any

from app.atoms.builder import build_atoms
from app.atoms.models import AtomBuildRequest, ParsedBlock, ParsedDocument, PipelineFailure
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
from app.segmenter.builder import build_segments
from app.segmenter.models import SegmentBuildRequest, SegmentPolicy

CLASSIFIER_RUNTIME_DISABLED = "CLASSIFIER_RUNTIME_DISABLED"
ANALYZE_CLASSIFIER_FAILED = "ANALYZE_CLASSIFIER_FAILED"


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
    text_inputs: list[tuple[int, object]],
    provider_result: ClassifierRuntimeProviderResult,
    embedding_loader: AtomEmbeddingModelLoader | None,
    *,
    verifier_config: AnalyzeVerifierConfig | None = None,
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

        atom_result = build_atoms(AtomBuildRequest(document=_document_for_input(item)))
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

        classification_result = provider_result.bundle.service.classify(
            SegmentClassificationRequest(
                input_id=input_id,
                segment_embeddings=segment_embedding_result.segment_embeddings,
                artifact=provider_result.bundle.artifact,
            )
        )
        if classification_result.failure is not None:
            return AnalyzeClassifierOutcome(enabled=True, failure=classification_result.failure)

        summary = project_classification_signal_summary(classification_result)
        has_candidates = has_candidates or bool(summary["has_candidates"])
        if summary["has_candidates"] and verifier_config is not None:
            verification_request = build_verification_request_from_classifier(
                input_id=input_id,
                classification=classification_result,
                artifact=verifier_config.artifact,
                timeout_ms=verifier_config.timeout_ms,
            )
            verification_result = verifier_config.service.verify(verification_request)
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


def _failure(code: str) -> PipelineFailure:
    return PipelineFailure(code=code, message=code, metadata={"failure_code": code})
