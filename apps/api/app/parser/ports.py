from typing import Protocol

from app.parser.models import (
    FileParserResult,
    ParserExecutionPlan,
    ParserPlanResolution,
    ParserWorkerPayload,
    ResolvedPlanRequest,
    ResolvedTemporaryFile,
    TempFileAccessContext,
    ParserPlanStep,
    ParserStepResult,
    StepKind,
)


class TemporaryFileResolverPort(Protocol):
    def resolve(self, file_ref: str, access_context: TempFileAccessContext) -> ResolvedTemporaryFile: ...


class ResolvedFileContentSourcePort(Protocol):
    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes: ...


class ParserPlanResolverPort(Protocol):
    def resolve(self, request: ResolvedPlanRequest) -> ParserPlanResolution: ...


class ParserPlanExecutorPort(Protocol):
    def execute(
        self,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
        plan: ParserExecutionPlan,
    ) -> FileParserResult: ...


class ParserStepAdapterPort(Protocol):
    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult: ...


class ParserAdapterRegistryPort(Protocol):
    def resolve_adapter(
        self,
        capability_id: str,
        step_kind: StepKind,
    ) -> ParserStepAdapterPort: ...


class FileParserRunnerPort(Protocol):
    def run(self, payload: ParserWorkerPayload) -> FileParserResult: ...
