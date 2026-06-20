from datetime import datetime, timedelta, timezone

import pytest

from app.parser.models import (
    ParserBoundaryError,
    TempFileAccessContext,
    TemporaryFileRecord,
)
from app.parser.temp_file_resolver import TemporaryFileResolver


NOW = datetime(2026, 6, 20, tzinfo=timezone.utc)
FILE_REF = "private-file-ref"
RUNTIME_REF = "private-runtime-ref"
PRIVATE_PATH = r"C:\private\original-secret.txt"
ORIGINAL_FILENAME = "original-secret.txt"
STORAGE_REF = "private-storage-ref"
PRIVATE_EXCEPTION = "PRIVATE REPOSITORY EXCEPTION"


class FakeTemporaryFileRecordRepository:
    def __init__(
        self,
        record: TemporaryFileRecord | None,
        exception: Exception | None = None,
    ) -> None:
        self.record = record
        self.exception = exception
        self.calls: list[str] = []

    def get(self, file_ref: str) -> TemporaryFileRecord | None:
        self.calls.append(file_ref)
        if self.exception is not None:
            raise self.exception
        return self.record


class FakeClock:
    def now(self) -> datetime:
        return NOW


def _context(**changes) -> TempFileAccessContext:
    values = {
        "authenticated_subject_id": "subject-1",
        "session_id": "session-1",
        "request_id": "request-1",
        "temp_scope_id": "scope-1",
    }
    values.update(changes)
    return TempFileAccessContext(**values)


def _record(**changes) -> TemporaryFileRecord:
    values = {
        "file_ref": FILE_REF,
        "authenticated_subject_id": "subject-1",
        "session_id": "session-1",
        "request_id": "request-1",
        "temp_scope_id": "scope-1",
        "state": "staged",
        "expires_at": NOW + timedelta(minutes=5),
        "deleted_at": None,
        "file_kind": "plain_text",
        "local_runtime_ref": RUNTIME_REF,
    }
    values.update(changes)
    return TemporaryFileRecord(**values)


def _resolve(record=None, *, context=None, exception=None):
    repository = FakeTemporaryFileRecordRepository(record, exception)
    resolver = TemporaryFileResolver(repository, FakeClock())
    return resolver.resolve(FILE_REF, context or _context()), repository


def _assert_failure(expected_code: str, record=None, *, context=None, exception=None, caplog):
    with pytest.raises(ParserBoundaryError) as raised:
        _resolve(record, context=context, exception=exception)

    failure = raised.value.failure
    assert failure.code == expected_code
    exposed = failure.message + repr(failure.metadata) + caplog.text
    for private_value in (
        FILE_REF,
        RUNTIME_REF,
        PRIVATE_PATH,
        ORIGINAL_FILENAME,
        STORAGE_REF,
        PRIVATE_EXCEPTION,
    ):
        assert private_value not in exposed


def test_resolves_staged_record_to_opaque_temporary_file():
    result, repository = _resolve(_record())

    assert result.file_ref == FILE_REF
    assert result.file_kind == "plain_text"
    assert result.local_runtime_ref == RUNTIME_REF
    assert set(result.model_fields_set) == {"file_ref", "file_kind", "local_runtime_ref"}
    assert repository.calls == [FILE_REF]


def test_scope_none_requires_both_record_and_context_to_be_none():
    result, _ = _resolve(_record(temp_scope_id=None), context=_context(temp_scope_id=None))

    assert result.file_kind == "plain_text"


def test_missing_record_is_sanitized(caplog):
    _assert_failure("TEMP_FILE_NOT_FOUND", caplog=caplog)


def test_subject_mismatch_is_sanitized(caplog):
    _assert_failure("TEMP_FILE_OWNER_MISMATCH", _record(authenticated_subject_id="subject-2"), caplog=caplog)


@pytest.mark.parametrize(
    ("record_changes", "context_changes"),
    [
        ({"request_id": "request-2"}, {}),
        ({"session_id": "session-2"}, {}),
        ({"session_id": None}, {}),
        ({"temp_scope_id": "scope-2"}, {}),
        ({"temp_scope_id": None}, {}),
        ({"temp_scope_id": "scope-1"}, {"temp_scope_id": None}),
    ],
)
def test_request_session_and_scope_mismatch_are_sanitized(
    record_changes, context_changes, caplog
):
    _assert_failure(
        "TEMP_FILE_SCOPE_MISMATCH",
        _record(**record_changes),
        context=_context(**context_changes),
        caplog=caplog,
    )


def test_expired_record_is_sanitized(caplog):
    _assert_failure(
        "TEMP_FILE_EXPIRED",
        _record(expires_at=NOW),
        caplog=caplog,
    )


def test_deleted_record_is_not_available(caplog):
    _assert_failure(
        "TEMP_FILE_RESOLVE_FAILED",
        _record(deleted_at=NOW - timedelta(seconds=1)),
        caplog=caplog,
    )


@pytest.mark.parametrize("state", ["processing", "consumed", "failed", "deleted", "unknown-state"])
def test_non_staged_or_unknown_state_is_not_available(state, caplog):
    _assert_failure("TEMP_FILE_RESOLVE_FAILED", _record(state=state), caplog=caplog)


def test_unknown_file_kind_is_unsupported(caplog):
    _assert_failure(
        "UNSUPPORTED_FILE_KIND",
        _record(file_kind="unknown-kind"),
        caplog=caplog,
    )


def test_repository_exception_is_sanitized(caplog):
    _assert_failure(
        "TEMP_FILE_RESOLVE_FAILED",
        exception=RuntimeError(
            f"{PRIVATE_EXCEPTION} {FILE_REF} {RUNTIME_REF} {PRIVATE_PATH} "
            f"{ORIGINAL_FILENAME} {STORAGE_REF}"
        ),
        caplog=caplog,
    )
