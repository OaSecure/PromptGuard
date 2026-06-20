from app.parser.models import (
    FileParserResult,
    ParserBoundaryError,
    ParserWorkerPayload,
    ResolvedPlanRequest,
    sanitized_failure,
)
from app.parser.ports import ParserPlanExecutorPort, ParserPlanResolverPort, TemporaryFileResolverPort


class FileParserRunner:
    def __init__(
        self,
        temporary_file_resolver: TemporaryFileResolverPort,
        plan_resolver: ParserPlanResolverPort,
        plan_executor: ParserPlanExecutorPort,
    ) -> None:
        self._temporary_file_resolver = temporary_file_resolver
        self._plan_resolver = plan_resolver
        self._plan_executor = plan_executor

    def run(self, payload: ParserWorkerPayload) -> FileParserResult:
        try:
            resolved_file = None
            if payload.input_kind == "file_reference":
                if payload.file_ref is None or payload.access_context is None:
                    return FileParserResult(
                        input_id=payload.input_id,
                        parser_status="failed",
                        failure=sanitized_failure("INVALID_PARSER_WORKER_PAYLOAD"),
                    )
                resolved_file = self._temporary_file_resolver.resolve(payload.file_ref, payload.access_context)

            resolution = self._plan_resolver.resolve(
                ResolvedPlanRequest(payload=payload, resolved_file=resolved_file)
            )
            if resolution.failure is not None or resolution.plan is None:
                return FileParserResult(
                    input_id=payload.input_id,
                    parser_status="failed",
                    failure=resolution.failure or sanitized_failure("PARSER_PLAN_RESOLVE_FAILED"),
                )
            return self._plan_executor.execute(payload, resolved_file, resolution.plan)
        except ParserBoundaryError as error:
            return FileParserResult(
                input_id=payload.input_id,
                parser_status="failed",
                failure=error.failure,
            )
        except Exception:
            return FileParserResult(
                input_id=payload.input_id,
                parser_status="failed",
                failure=sanitized_failure("PARSER_WORKER_FAILED"),
            )
