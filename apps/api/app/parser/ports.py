from typing import Protocol

from app.parser.models import (
    FileParserResult,
    ParserExecutionPlanStub,
    ParserPlanResolution,
    ParserWorkerPayload,
    ResolvedPlanRequest,
    ResolvedTemporaryFile,
    TempFileAccessContext,
)


class TemporaryFileResolverPort(Protocol):
    def resolve(self, file_ref: str, access_context: TempFileAccessContext) -> ResolvedTemporaryFile: ...


class ParserPlanResolverPort(Protocol):
    def resolve(self, request: ResolvedPlanRequest) -> ParserPlanResolution: ...


class ParserPlanExecutorPort(Protocol):
    def execute(
        self,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
        plan: ParserExecutionPlanStub,
    ) -> FileParserResult: ...


class FileParserRunnerPort(Protocol):
    def run(self, payload: ParserWorkerPayload) -> FileParserResult: ...
