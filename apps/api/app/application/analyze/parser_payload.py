from typing import Any, Literal

from app.application.analyze.input_envelope import InputEnvelope
from app.domain.types.common import ExtractionRequirement
from app.domain.types.parser import FileMetadata
from app.parser.models import ParserWorkerPayload, TempFileAccessContext

FileReferenceInputOrigin = Literal["pasted_file_ref", "pasted_image_ref", "screenshot_image_ref", "attached_file_ref"]
FILE_REFERENCE_INPUT_ORIGINS: dict[str, FileReferenceInputOrigin] = {
    "attached_file": "attached_file_ref",
    "pasted_file": "pasted_file_ref",
    "pasted_image": "pasted_image_ref",
    "screenshot_image": "screenshot_image_ref",
}

_FILE_REFERENCE_ORIGINS = {
    "pasted_file_ref",
    "pasted_image_ref",
    "screenshot_image_ref",
    "attached_file_ref",
}
_TEXT_ORIGINS = {"composer_text", "converted_paste_text"}


def build_parser_worker_payload(
    envelope: InputEnvelope,
    *,
    access_context: TempFileAccessContext | None,
) -> ParserWorkerPayload | None:
    if envelope.input_origin in _TEXT_ORIGINS:
        return ParserWorkerPayload(
            input_id=envelope.input_id,
            request_id=envelope.request_id,
            input_kind="text_wrapper",
            extraction_requirement=envelope.extraction_requirement,
            text=envelope.text,
        )

    if envelope.input_origin in _FILE_REFERENCE_ORIGINS:
        if access_context is None:
            raise ValueError("file_reference requires access_context")
        return ParserWorkerPayload(
            input_id=envelope.input_id,
            request_id=envelope.request_id,
            input_kind="file_reference",
            extraction_requirement=envelope.extraction_requirement,
            file_ref=envelope.file_ref,
            file_kind=envelope.file_kind,
            access_context=access_context,
        )

    return None


def build_file_reference_parser_worker_payload(
    request_id: str,
    item: Any,
    *,
    access_context: TempFileAccessContext,
) -> ParserWorkerPayload:
    payload = build_parser_worker_payload(
        InputEnvelope(
            input_id=item.input_id,
            request_id=request_id,
            input_origin=FILE_REFERENCE_INPUT_ORIGINS[item.source],
            file_kind=item.file_kind,
            extraction_requirement=_extraction_requirement_for_file_kind(item.file_kind),
            file_ref=item.file_ref,
            metadata=FileMetadata(
                file_kind=item.file_kind,
                size_bucket=item.size_bucket or "unknown",
                mime_hint=item.mime,
                extension_hint=item.extension,
            ),
        ),
        access_context=access_context,
    )
    if payload is None:
        raise ValueError("file_reference requires parser payload")
    return payload


def _extraction_requirement_for_file_kind(file_kind: str | None) -> ExtractionRequirement:
    if file_kind == "image":
        return "ocr_required"
    if file_kind == "pdf":
        return "native_parse_then_ocr_fallback"
    if file_kind in {"plain_text", "code", "office_document", "spreadsheet", "slide"}:
        return "native_parse"
    return "metadata_only"
