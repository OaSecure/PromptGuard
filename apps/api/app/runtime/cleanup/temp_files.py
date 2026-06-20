from datetime import datetime
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage


class TempFileCleanupService:
    def __init__(self, storage: EncryptedTemporaryFileStorage): self.storage = storage
    def after_analyze(self, file_ref: str) -> bool: return self.storage.delete(file_ref)
    def sweep(self, now: datetime | None = None) -> list[str]: return self.storage.sweep_expired(now)
