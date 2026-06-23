from app.application.analyze.input_envelope import InputEnvelope
from app.parser.models import ParserWorkerPayload, TempFileAccessContext

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
