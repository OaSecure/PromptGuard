from typing import Literal

from pydantic import BaseModel, model_validator

from app.domain.types.common import ExtractionRequirement, FileKind
from app.domain.types.parser import FileMetadata


class InputEnvelope(BaseModel):
    input_id: str
    request_id: str
    input_origin: Literal["composer_text", "converted_paste_text", "pasted_file_ref", "pasted_image_ref", "screenshot_image_ref", "attached_file_ref", "attachment_metadata", "unsupported_attachment"]
    file_kind: FileKind | None
    extraction_requirement: ExtractionRequirement
    file_ref: str | None = None
    text: str | None = None
    metadata: FileMetadata | None = None

    @model_validator(mode="after")
    def content_matches_origin(self) -> "InputEnvelope":
        if self.input_origin in {"composer_text", "converted_paste_text"}:
            if self.text is None or self.file_ref is not None or self.file_kind is not None:
                raise ValueError("text origins require text and forbid file fields")
        elif self.input_origin.endswith("_ref"):
            if self.file_ref is None or self.text is not None or self.file_kind is None:
                raise ValueError("file reference origins require file_ref/file_kind and forbid text")
        elif self.text is not None:
            raise ValueError("metadata-only origins forbid text")
        return self
