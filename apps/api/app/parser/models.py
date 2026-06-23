from datetime import datetime
from typing import Literal

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
PlanKind = Literal[
    "wrap_text", "native_text", "pdf_native_then_page_ocr", "pdf_native", "image_ocr",
    "office_parse", "spreadsheet_parse", "slide_parse", "code_parse",
    "metadata_only", "unsupported",
]
StepKind = Literal[
    "wrap_text", "native_text_extract", "pdf_native_text_extract", "pdf_coverage_evaluate",
    "render_ocr_candidate_pages", "ocr_primary", "ocr_fallback", "merge_blocks",
    "image_ocr", "office_parse", "spreadsheet_parse", "slide_parse", "code_parse",
]
FallbackTrigger = Literal[
    "adapter_unavailable", "adapter_initialization_failed", "step_failed", "no_text_detected"
]


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


class TemporaryFileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file_ref: str
    authenticated_subject_id: str
    session_id: str | None
    request_id: str
    temp_scope_id: str | None = None
    state: str
    expires_at: datetime
    deleted_at: datetime | None = None
    file_kind: str
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


class ParserPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    ordinal: int = Field(ge=0)
    step_kind: StepKind
    capability_id: str
    execution_mode: Literal["always", "fallback"] = "always"


class ParserFallbackRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    source_step_id: str
    trigger: FallbackTrigger
    target_step_id: str
    ordinal: int = Field(ge=0)


class ParserExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str
    plan_kind: PlanKind
    steps: tuple[ParserPlanStep, ...]
    fallback_rules: tuple[ParserFallbackRule, ...] = ()

    @model_validator(mode="after")
    def validate_plan_graph(self) -> "ParserExecutionPlan":
        if not self.steps and self.plan_kind not in {"metadata_only", "unsupported"}:
            raise ValueError("executable plans require steps")
        step_ordinals = [step.ordinal for step in self.steps]
        if step_ordinals != list(range(len(self.steps))):
            raise ValueError("step ordinals must be unique, ordered, and contiguous")
        rule_ordinals = [rule.ordinal for rule in self.fallback_rules]
        if rule_ordinals != list(range(len(self.fallback_rules))):
            raise ValueError("fallback rule ordinals must be unique, ordered, and contiguous")
        steps_by_id = {step.step_id: step for step in self.steps}
        if len(steps_by_id) != len(self.steps):
            raise ValueError("step ids must be unique")
        _validate_fallback_graph(steps_by_id, self.fallback_rules)
        return self


def _validate_fallback_graph(
    steps_by_id: dict[str, ParserPlanStep],
    rules: tuple[ParserFallbackRule, ...],
) -> None:
    routes: set[tuple[str, FallbackTrigger]] = set()
    for rule in rules:
        source = steps_by_id.get(rule.source_step_id)
        if source is None or source.execution_mode == "fallback":
            raise ValueError("fallback source must be an existing non-fallback step")
        target = steps_by_id.get(rule.target_step_id)
        if target is None or target.execution_mode != "fallback":
            raise ValueError("fallback target must be an existing fallback step")
        route = (rule.source_step_id, rule.trigger)
        if route in routes:
            raise ValueError("fallback source and trigger route must be unique")
        routes.add(route)


class ParserAdapterCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    step_kinds: tuple[StepKind, ...]
    enabled: bool = True
    license_allowed: bool = True


class ParserPlanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enable_native_parsing: bool = True
    enable_ocr: bool = True


class ParserLicensePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    denied_capability_ids: tuple[str, ...] = ()


class ParserPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: ParserWorkerPayload
    resolved_file: ResolvedTemporaryFile | None = None
    config: ParserPlanConfig
    capabilities: tuple[ParserAdapterCapability, ...]
    license_policy: ParserLicensePolicy


class ParserStepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    status: Literal["success", "partial", "failed", "skipped"]
    trigger: FallbackTrigger | None = None
    document: ParsedDocument | None = None
    failure: PipelineFailure | None = None



class FileParserResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str
    document: ParsedDocument | None = None
    parser_status: ParserStatus
    ocr_status: OcrStatus = "not_applicable"
    failure: PipelineFailure | None = None


class ParserPlanResolution(BaseModel):
    plan: ParserExecutionPlan | None = None
    failure: PipelineFailure | None = None


class ResolvedPlanRequest(BaseModel):
    payload: ParserWorkerPayload
    resolved_file: ResolvedTemporaryFile | None = None


class ParserBoundaryError(Exception):
    def __init__(self, failure: PipelineFailure) -> None:
        super().__init__(failure.code)
        self.failure = failure


def sanitized_failure(code: str) -> PipelineFailure:
    return PipelineFailure(code=code, message=code, metadata={"failure_code": code})
