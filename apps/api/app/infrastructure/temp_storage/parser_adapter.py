from datetime import datetime

from app.infrastructure.temp_storage.filesystem import (
    EncryptedTemporaryFileStorage,
    TempFileError,
)
from app.infrastructure.temp_storage.filesystem import (
    TempFileAccessContext as StorageAccessContext,
)
from app.parser.models import ResolvedTemporaryFile, TemporaryFileRecord
from app.parser.ports import ResolvedFileContentSourcePort, TemporaryFileRecordRepositoryPort
from app.ports.clock import ClockPort


class TemporaryStorageParserRepository(TemporaryFileRecordRepositoryPort):
    def __init__(self, storage: EncryptedTemporaryFileStorage) -> None:
        self._storage = storage

    def get(self, file_ref: str) -> TemporaryFileRecord | None:
        try:
            manifest = self._storage.manifest(file_ref)
        except TempFileError:
            return None
        return TemporaryFileRecord(
            file_ref=file_ref,
            authenticated_subject_id=manifest["subject_id"],
            session_id=manifest["subject_id"],
            request_id=manifest["request_id"],
            temp_scope_id=manifest["temp_scope_id"],
            state="staged",
            expires_at=datetime.fromisoformat(manifest["expires_at"]),
            deleted_at=None,
            file_kind=manifest["file_kind"],
            local_runtime_ref=file_ref,
        )


class TemporaryStorageContentSource(ResolvedFileContentSourcePort):
    def __init__(self, storage: EncryptedTemporaryFileStorage, clock: ClockPort) -> None:
        self._storage = storage
        self._clock = clock

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        manifest = self._storage.manifest(resolved_file.local_runtime_ref)
        return self._storage.resolve(
            resolved_file.local_runtime_ref,
            StorageAccessContext(
                authenticated_subject_id=manifest["subject_id"],
                request_id=manifest["request_id"],
                temp_scope_id=manifest["temp_scope_id"],
            ),
            self._clock.now(),
        )
