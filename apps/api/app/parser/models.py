from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.atoms.models import ParsedDocument, PipelineFailure

FileKind = Literal[
    "plain_text", "image", "pdf", "office_document", "spreadsheet", "slide", "code", "unknown"
]
ExtractionRequirement = Literal[
    "wrap_text",
    "native_parse",
    "ocr_required",
    "native_parse_then_ocr_fallback",
    "metadata_only",
    "unsupported",
    "not_applicable",
]
ParserStatus = Literal["parsed", "partial", "failed", "unsupported", "timeout", "too_large", "encrypted"]
OcrStatus = Literal["not_applicable", "text_found", "no_text_detected", "timeout", "failed"]


class TempFileAccessContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authenticated_subject_id: str
    session_id: str
    request_id: str
    temp_scope_id: str | None = None


class ResolvedTemporaryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_ref: str
    file_kind: FileKind
    local_runtime_ref: str


class ParserWorkerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str
    request_id: str
    input_kind: Literal["text_wrapper", "file_reference"]
    extraction_requirement: ExtractionRequirement
    file_ref: str | None = None
    file_kind: FileKind | None = None
    text: str | None = None
    access_context: TempFileAccessContext | None = None

    @model_validator(mode="after")
    def validate_input_shape(self) -> "ParserWorkerPayload":
        if self.input_kind == "file_reference":
            if not self.file_ref:
                raise ValueError("file_reference requires file_ref")
            if self.text is not None:
                raise ValueError("file_reference forbids text")
            if self.access_context is None:
                raise ValueError("file_reference requires access_context")
        elif self.file_ref is not None or self.access_context is not None:
            raise ValueError("text_wrapper forbids file reference fields")
        return self


class ParserExecutionPlanStub(BaseModel):
    """Opaque placeholder. Typed steps and fallback rules belong to PR5."""

    model_config = ConfigDict(extra="forbid")
    plan_id: str


class FileParserResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str
    document: ParsedDocument | None = None
    parser_status: ParserStatus
    ocr_status: OcrStatus = "not_applicable"
    failure: PipelineFailure | None = None


class ParserPlanResolution(BaseModel):
    plan: ParserExecutionPlanStub | None = None
    failure: PipelineFailure | None = None


class ResolvedPlanRequest(BaseModel):
    payload: ParserWorkerPayload
    resolved_file: ResolvedTemporaryFile | None = None


def sanitized_failure(code: str) -> PipelineFailure:
    return PipelineFailure(code=code, message=code, metadata={"failure_code": code})
