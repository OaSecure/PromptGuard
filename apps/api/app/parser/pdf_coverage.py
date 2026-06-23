import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERY_LOW_MEANINGFUL_CHARS_PER_PAGE = 30
LOW_MEANINGFUL_CHARS_PER_PAGE = 120
LOW_NATIVE_TEXT_PAGE_RATIO_THRESHOLD = 0.80

NativeExtractionStatus = Literal["success", "failed"]
ImageEvidence = Literal["present", "absent", "unknown"]
MeaningfulCountBucket = Literal["zero", "very_low", "low", "sufficient"]
CandidateReason = Literal[
    "native_extraction_failed",
    "very_low_native_text",
    "low_native_text_image_present",
    "low_native_text_image_unknown",
    "low_native_text_image_absent",
    "sufficient_native_text",
]


class PdfPageCoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_index: int = Field(ge=1)
    native_extraction_status: NativeExtractionStatus
    meaningful_character_count: int = Field(ge=0)
    image_evidence: ImageEvidence


class PdfPageCoverageDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_index: int = Field(ge=1)
    count_bucket: MeaningfulCountBucket
    image_evidence: ImageEvidence
    is_ocr_candidate: bool
    candidate_reason: CandidateReason
    selected_for_ocr: bool = False


class PdfCoverageAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_pages: int = Field(ge=0)
    candidate_page_count: int = Field(ge=0)
    low_native_text_page_ratio: float = Field(ge=0, le=1)
    low_native_text_ratio_warning: bool
    selected_candidate_pages: tuple[int, ...]
    skipped_candidate_count: int = Field(ge=0)


class PdfCoverageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pages: tuple[PdfPageCoverageDecision, ...]
    aggregate: PdfCoverageAggregate


class PdfCoverageEvaluator:
    """Apply the development-contract PR8 page-local PDF coverage defaults."""

    def evaluate(
        self,
        pages: list[PdfPageCoverageInput] | tuple[PdfPageCoverageInput, ...],
        max_ocr_pages: int,
    ) -> PdfCoverageResult:
        if max_ocr_pages < 0:
            raise ValueError("PDF_COVERAGE_INVALID_LIMIT")
        page_indexes = [page.page_index for page in pages]
        if len(page_indexes) != len(set(page_indexes)):
            raise ValueError("PDF_COVERAGE_DUPLICATE_PAGE")

        decisions = [self._evaluate_page(page) for page in sorted(pages, key=lambda page: page.page_index)]
        candidate_indexes = [
            decision.page_index for decision in decisions if decision.is_ocr_candidate
        ]
        selected_indexes = tuple(candidate_indexes[:max_ocr_pages])
        selected_set = set(selected_indexes)
        selected_decisions = tuple(
            decision.model_copy(update={"selected_for_ocr": decision.page_index in selected_set})
            for decision in decisions
        )
        candidate_count = len(candidate_indexes)
        total_pages = len(decisions)
        ratio = candidate_count / total_pages if total_pages else 0.0
        return PdfCoverageResult(
            pages=selected_decisions,
            aggregate=PdfCoverageAggregate(
                total_pages=total_pages,
                candidate_page_count=candidate_count,
                low_native_text_page_ratio=ratio,
                low_native_text_ratio_warning=(
                    ratio >= LOW_NATIVE_TEXT_PAGE_RATIO_THRESHOLD and total_pages > 0
                ),
                selected_candidate_pages=selected_indexes,
                skipped_candidate_count=candidate_count - len(selected_indexes),
            ),
        )

    @staticmethod
    def _evaluate_page(page: PdfPageCoverageInput) -> PdfPageCoverageDecision:
        count = page.meaningful_character_count
        bucket = _count_bucket(count)
        if page.native_extraction_status == "failed":
            candidate, reason = True, "native_extraction_failed"
        elif count < VERY_LOW_MEANINGFUL_CHARS_PER_PAGE:
            candidate, reason = True, "very_low_native_text"
        elif count < LOW_MEANINGFUL_CHARS_PER_PAGE and page.image_evidence == "present":
            candidate, reason = True, "low_native_text_image_present"
        elif count < LOW_MEANINGFUL_CHARS_PER_PAGE and page.image_evidence == "unknown":
            candidate, reason = True, "low_native_text_image_unknown"
        elif count < LOW_MEANINGFUL_CHARS_PER_PAGE:
            candidate, reason = False, "low_native_text_image_absent"
        else:
            candidate, reason = False, "sufficient_native_text"
        return PdfPageCoverageDecision(
            page_index=page.page_index,
            count_bucket=bucket,
            image_evidence=page.image_evidence,
            is_ocr_candidate=candidate,
            candidate_reason=reason,
        )


def count_meaningful_characters(text: str) -> int:
    """Count NFKC-normalized Unicode letters and numbers without retaining text."""
    normalized = unicodedata.normalize("NFKC", text)
    return sum(unicodedata.category(character)[0] in {"L", "N"} for character in normalized)


def _count_bucket(count: int) -> MeaningfulCountBucket:
    if count == 0:
        return "zero"
    if count < VERY_LOW_MEANINGFUL_CHARS_PER_PAGE:
        return "very_low"
    if count < LOW_MEANINGFUL_CHARS_PER_PAGE:
        return "low"
    return "sufficient"
