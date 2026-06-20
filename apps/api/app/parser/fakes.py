import time

from app.atoms.models import ParsedDocument
from app.parser.models import (
    FileParserResult,
    ParserBoundaryError,
    ParserExecutionPlan,
    ParserPlanResolution,
    ParserWorkerPayload,
    ResolvedPlanRequest,
    ResolvedTemporaryFile,
    TempFileAccessContext,
    sanitized_failure,
    ParserPlanStep,
    ParserStepResult,
)


class FakeTemporaryFileResolver:
    def __init__(self, failure_code: str | None = None) -> None:
        self.failure_code = failure_code
        self.calls: list[tuple[str, TempFileAccessContext]] = []

    def resolve(self, file_ref: str, access_context: TempFileAccessContext) -> ResolvedTemporaryFile:
        self.calls.append((file_ref, access_context))
        if self.failure_code:
            raise ParserBoundaryError(sanitized_failure(self.failure_code))
        return ResolvedTemporaryFile(
            file_ref=file_ref,
            file_kind="unknown",
            local_runtime_ref="runtime-only-ref",
        )


class FakeParserPlanResolver:
    def __init__(self, failure_code: str | None = None) -> None:
        self.failure_code = failure_code
        self.calls: list[ResolvedPlanRequest] = []

    def resolve(self, request: ResolvedPlanRequest) -> ParserPlanResolution:
        self.calls.append(request)
        if self.failure_code:
            return ParserPlanResolution(failure=sanitized_failure(self.failure_code))
        return ParserPlanResolution(plan=ParserExecutionPlan(
            plan_id="fake-plan", plan_kind="metadata_only", steps=()
        ))


class FakeParserPlanExecutor:
    def __init__(self, failure_code: str | None = None) -> None:
        self.failure_code = failure_code
        self.calls: list[ResolvedPlanRequest] = []

    def execute(self, payload, resolved_file, plan) -> FileParserResult:
        self.calls.append(ResolvedPlanRequest(payload=payload, resolved_file=resolved_file))
        if self.failure_code:
            return FileParserResult(
                input_id=payload.input_id,
                parser_status="failed",
                failure=sanitized_failure(self.failure_code),
            )
        return FileParserResult(
            input_id=payload.input_id,
            document=ParsedDocument(input_id=payload.input_id, blocks=[]),
            parser_status="parsed",
        )


class FakeParserStepAdapter:
    def __init__(self, results: dict[str, ParserStepResult] | None = None, exception_message: str | None = None) -> None:
        self.results = results or {}
        self.exception_message = exception_message
        self.calls: list[str] = []

    def execute_step(self, step: ParserPlanStep, payload, resolved_file) -> ParserStepResult:
        self.calls.append(step.step_id)
        if self.exception_message is not None:
            raise RuntimeError(self.exception_message)
        return self.results.get(step.step_id, ParserStepResult(step_id=step.step_id, status="success"))


class FakeFileParserRunner:
    def __init__(self, delay_seconds: float = 0) -> None:
        self.delay_seconds = delay_seconds
        self.payloads: list[ParserWorkerPayload] = []

    def run(self, payload: ParserWorkerPayload) -> FileParserResult:
        self.payloads.append(payload)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        return FileParserResult(input_id=payload.input_id, parser_status="parsed")


class RaisingFileParserRunner:
    def __init__(self, exception_message: str) -> None:
        self.exception_message = exception_message

    def run(self, payload: ParserWorkerPayload) -> FileParserResult:
        raise RuntimeError(self.exception_message)
