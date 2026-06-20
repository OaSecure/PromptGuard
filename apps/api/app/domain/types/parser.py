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
    input_id: str
    request_id: str
    file_ref: str | None = None
    text: str | None = None
    file_kind: FileKind | None
    extraction_requirement: ExtractionRequirement


class TempFileAccessContext(BaseModel):
    request_id: str
    session_id: str
    owner_id: str


class ResolvedTemporaryFile(BaseModel):
    opaque_handle: str
    metadata: FileMetadata


class ParserPlanStep(BaseModel):
    step_type: ParserStepType
    adapter_id: str | None = None


class ParserFallbackRule(BaseModel):
    from_step: ParserStepType
    on_status: ParserStatus
    to_step: ParserStepType


class ParserExecutionPlan(BaseModel):
    plan_kind: ParserPlanKind
    steps: list[ParserPlanStep]
    fallback_rules: list[ParserFallbackRule] = Field(default_factory=list)
    limits: ParserLimits


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
