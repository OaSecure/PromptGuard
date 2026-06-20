from app.parser.models import (
    FileKind,
    ParserBoundaryError,
    ResolvedTemporaryFile,
    TempFileAccessContext,
    sanitized_failure,
)
from app.parser.ports import TemporaryFileRecordRepositoryPort
from app.ports.clock import ClockPort


SUPPORTED_FILE_KINDS: tuple[FileKind, ...] = (
    "plain_text",
    "image",
    "pdf",
    "office_document",
    "spreadsheet",
    "slide",
    "code",
)


class TemporaryFileResolver:
    def __init__(
        self,
        repository: TemporaryFileRecordRepositoryPort,
        clock: ClockPort,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def resolve(
        self,
        file_ref: str,
        access_context: TempFileAccessContext,
    ) -> ResolvedTemporaryFile:
        try:
            record = self._repository.get(file_ref)
        except Exception:
            self._raise("TEMP_FILE_RESOLVE_FAILED")

        if record is None:
            self._raise("TEMP_FILE_NOT_FOUND")
        if record.authenticated_subject_id != access_context.authenticated_subject_id:
            self._raise("TEMP_FILE_OWNER_MISMATCH")
        if (
            record.request_id != access_context.request_id
            or record.session_id != access_context.session_id
            or record.temp_scope_id != access_context.temp_scope_id
        ):
            self._raise("TEMP_FILE_SCOPE_MISMATCH")
        if record.expires_at <= self._clock.now():
            self._raise("TEMP_FILE_EXPIRED")
        if record.state != "staged" or record.deleted_at is not None:
            self._raise("TEMP_FILE_RESOLVE_FAILED")
        if record.file_kind not in SUPPORTED_FILE_KINDS:
            self._raise("UNSUPPORTED_FILE_KIND")

        return ResolvedTemporaryFile(
            file_ref=record.file_ref,
            file_kind=record.file_kind,
            local_runtime_ref=record.local_runtime_ref,
        )

    @staticmethod
    def _raise(code: str) -> None:
        raise ParserBoundaryError(sanitized_failure(code))
