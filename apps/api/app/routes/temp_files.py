import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import get_settings
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.models.auth import User
from app.routes.auth import require_active_user

router = APIRouter(prefix="/files", tags=["files"])
FILE_KINDS = {"plain_text", "image", "pdf", "office_document", "spreadsheet", "slide", "code", "unknown"}
SAFE_MIME = re.compile(r"^[a-z0-9.+-]+/[a-z0-9.+-]+$")
SAFE_EXTENSION = re.compile(r"^[a-z0-9]{1,16}$")


class TempUploadResponse(BaseModel):
    file_ref: str
    file_kind: str
    mime_hint: str | None
    extension_hint: str | None
    size_bucket: Literal["empty", "tiny", "small"]
    expires_at: datetime


@lru_cache
def get_temp_storage() -> EncryptedTemporaryFileStorage:
    settings = get_settings()
    return EncryptedTemporaryFileStorage(Path(settings.temp_file_dir), settings.temp_file_encryption_key, settings.temp_file_ttl_seconds)


def validate_temp_storage_settings() -> None:
    get_temp_storage()


@router.post("/temp", response_model=TempUploadResponse)
async def upload_temp_file(file: UploadFile = File(...), request_id: str = Form(...), file_kind: str = Form(...),
                           mime_hint: str | None = Form(default=None), extension_hint: str | None = Form(default=None),
                           current_user: User = Depends(require_active_user), storage: EncryptedTemporaryFileStorage = Depends(get_temp_storage)) -> TempUploadResponse:
    settings = get_settings()
    if file_kind not in FILE_KINDS: raise HTTPException(status_code=422, detail="unsupported file kind")
    mime = mime_hint.casefold().strip() if mime_hint and SAFE_MIME.fullmatch(mime_hint.casefold().strip()) else None
    extension = extension_hint.casefold().strip().lstrip(".") if extension_hint else None
    extension = extension if extension and SAFE_EXTENSION.fullmatch(extension) else None
    chunks, total = [], 0
    while chunk := await file.read(65_536):
        total += len(chunk)
        if total > settings.temp_file_max_bytes: raise HTTPException(status_code=413, detail="temporary file is too large")
        chunks.append(chunk)
    bucket = "empty" if total == 0 else "tiny" if total <= 16_384 else "small"
    stored = storage.store(b"".join(chunks), subject_id=str(current_user.id), request_id=request_id, file_kind=file_kind,
                           mime_hint=mime, extension_hint=extension, size_bucket=bucket)
    return TempUploadResponse(**{key: stored[key] for key in TempUploadResponse.model_fields})
