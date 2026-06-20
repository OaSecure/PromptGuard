from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

JsonValue = str | int | float | bool | None | dict[str, Any] | list[Any]
FileKind = Literal["plain_text", "image", "pdf", "office_document", "spreadsheet", "slide", "code", "unknown"]
SizeBucket = Literal["empty", "tiny", "small", "medium", "large", "huge", "unknown"]
ParserStatus = Literal["parsed", "partial", "failed", "unsupported", "timeout", "too_large", "encrypted"]
OcrStatus = Literal["not_applicable", "text_found", "no_text_detected", "timeout", "failed"]
ScannerStatus = Literal["not_started", "completed", "partial", "timeout", "failed"]
ExtractionRequirement = Literal["wrap_text", "native_parse", "ocr_required", "native_parse_then_ocr_fallback", "metadata_only", "unsupported", "not_applicable"]
ParserPlanKind = Literal["wrap_text", "native_text", "pdf_native_then_page_ocr", "image_ocr", "office_parse", "spreadsheet_parse", "slide_parse", "code_parse", "metadata_only", "unsupported"]
ParserStepType = Literal["wrap_text", "native_text_extract", "pdf_native_text_extract", "pdf_coverage_evaluate", "render_ocr_candidate_pages", "ocr_primary", "ocr_fallback", "office_parse", "spreadsheet_parse", "slide_parse", "code_parse", "merge_blocks", "metadata_only", "unsupported"]
ReasonCode = Literal["NO_RISK_DETECTED", "LEXICAL_DETERMINISTIC_SECRET_SIGNAL", "LEXICAL_HIGH_RISK_PII_SIGNAL", "PROTECTED_TARGET_STRONG_SIGNAL", "RISK_CONTEXT_VERIFIER_CONFIRMED", "RISK_CONTEXT_LR_ONLY", "RISK_CONTEXT_LR_ONLY_VERIFIER_TIMEOUT", "RISK_CONTEXT_LR_ONLY_VERIFIER_FAILED", "RISK_CONTEXT_VERIFIER_UNCERTAIN", "CONTENT_NOT_SCANNED", "PARSER_OR_OCR_FAILED", "UNSUPPORTED_FILE", "EMPTY_INPUT", "INTERNAL_POLICY_REASON_UNMAPPED"]


class TextRange(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def half_open_range(self) -> "TextRange":
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start")
        return self


class OffsetMapping(BaseModel):
    normalized_start: int = Field(ge=0)
    normalized_end: int = Field(ge=0)
    original_start: int = Field(ge=0)
    original_end: int = Field(ge=0)

    @model_validator(mode="after")
    def ranges_are_half_open(self) -> "OffsetMapping":
        if self.normalized_end < self.normalized_start or self.original_end < self.original_start:
            raise ValueError("mapping ranges must be half-open")
        return self


class PipelineFailure(BaseModel):
    code: str
    message: str
    retryable: bool
    module: str | None = None


class ScanStatus(BaseModel):
    parser_status: ParserStatus
    ocr_status: OcrStatus
    scanner_status: ScannerStatus = "not_started"
