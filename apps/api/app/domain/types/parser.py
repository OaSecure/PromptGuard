from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .common import ExtractionRequirement, FileKind, JsonValue, OcrStatus, ParserPlanKind, ParserStatus, ParserStepType, PipelineFailure, SizeBucket

BlockSource = Literal["text_wrapper", "native_parser", "ocr", "spreadsheet", "slide", "code"]
ExtractionStatus = Literal["extracted", "partial", "empty", "failed"]


class BlockLocation(BaseModel):
    page: int | None = Field(default=None, ge=1)
    sheet_index: int | None = Field(default=None, ge=0)
    slide: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)


class ParsedBlock(BaseModel):
    block_id: str
    input_id: str
    text: str
    source: BlockSource
    location: BlockLocation | None = None
    extraction_status: ExtractionStatus


class ParsedDocument(BaseModel):
    input_id: str
    file_ref: str | None
    file_kind: FileKind | None
    parser_id: str
    parser_version: str
    parser_status: ParserStatus
    ocr_status: OcrStatus
    blocks: list[ParsedBlock]
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def file_kind_matches_reference(self) -> "ParsedDocument":
        if self.file_ref is not None and self.file_kind is None:
            raise ValueError("file references require file_kind; use unknown when unresolved")
        return self


class FileParserResult(BaseModel):
    input_id: str
    document: ParsedDocument | None
    parser_status: ParserStatus
    ocr_status: OcrStatus
    failure: PipelineFailure | None = None


class FileMetadata(BaseModel):
    file_kind: FileKind
    size_bucket: SizeBucket
    mime_hint: str | None = None
    extension_hint: str | None = None


class ParserLimits(BaseModel):
    max_bytes: int = Field(gt=0)
    timeout_ms: int = Field(gt=0)
    max_pages: int = Field(gt=0)


class ParserWorkerPayload(BaseModel):
    request_id: str
    input_id: str
    input_origin: Literal["composer_text", "converted_paste_text", "pasted_file_ref", "pasted_image_ref", "screenshot_image_ref", "attached_file_ref"]
    file_kind: FileKind | None
    extraction_requirement: ExtractionRequirement
    file_ref: str | None
    text: str | None
    metadata: FileMetadata
    parser_limits: ParserLimits
    access_context: "TempFileAccessContext | None" = None


class TempFileAccessContext(BaseModel):
    authenticated_subject_id: str
    session_id: str
    request_id: str
    temp_scope_id: str | None = None


class ResolvedTemporaryFile(BaseModel):
    opaque_handle: str
    metadata: FileMetadata


class ParserPlanStep(BaseModel):
    step_id: str
    ordinal: int = Field(ge=0)
    step_type: ParserStepType
    adapter_id: str | None = None
    condition: str | None = None
    required: bool = True
    on_failure: Literal["fail", "partial", "continue", "apply_fallback"] = "fail"


class ParserFallbackRule(BaseModel):
    rule_id: str
    trigger: str
    fallback_action: Literal["run_step", "mark_partial", "mark_unsupported", "emit_failure"]
    fallback_target: str | None = None
    failure_code: str


class ParserExecutionPlan(BaseModel):
    plan_id: str
    plan_kind: ParserPlanKind
    input_id: str
    steps: list[ParserPlanStep]
    fallback_rules: list[ParserFallbackRule] = Field(default_factory=list)
    unsupported_reason_code: str | None = None

    @model_validator(mode="after")
    def steps_are_ordered(self) -> "ParserExecutionPlan":
        ordinals = [step.ordinal for step in self.steps]
        if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
            raise ValueError("steps must have unique ascending ordinals")
        return self


class ComponentLicenseMetadata(BaseModel):
    component: str
    version: str
    license_id: str
    artifact_ref: str


class OcrImageInput(BaseModel):
    image_handle: str
    page: int | None = Field(default=None, ge=1)


class OcrOptions(BaseModel):
    languages: list[str] = Field(default_factory=list)
    timeout_ms: int = Field(gt=0)


class OcrTextBlock(BaseModel):
    text: str
    confidence_bucket: Literal["low", "medium", "high", "unknown"]
    location: BlockLocation | None = None


class OcrResult(BaseModel):
    status: OcrStatus
    blocks: list[OcrTextBlock] = Field(default_factory=list)
    engine_id: str
    failure: PipelineFailure | None = None
