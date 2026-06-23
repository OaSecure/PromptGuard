import json
import re
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.types.common import FileKind, SizeBucket

# PR1 defines internal v3 contracts but no shared version constant. Keep the
# compatibility version owned by this HTTP boundary until a shared constant exists.
ANALYZE_SCHEMA_VERSION: Final[Literal["v3"]] = "v3"

TEXT_SOURCES = ("composer", "converted_paste")
TEXT_SOURCE_LIMITS = {"composer": 262_144, "converted_paste": 1_048_576}
FORBIDDEN_METADATA_KEYS = {"name", "filename", "file_name", "original_filename", "path", "url"}
SECRET_LIKE_ID_RE = re.compile(r"(?:gh[pousr]_|sk-[A-Za-z0-9]|xox[baprs]-|AKIA[0-9A-Z]|postgres://|mysql://|bearer|private[_-]?key)", re.IGNORECASE)
SAFE_TEMP_SCOPE_ID_RE = re.compile(r"^tscope_[A-Za-z0-9_-]{24,}$")


class LegacyAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    filter_config_revision: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
    context: "LegacyAnalyzeContext"
    inputs: list["LegacyAnalyzeInput"] = Field(min_length=1, max_length=20)

    @field_validator("client_request_id", "filter_config_revision")
    @classmethod
    def ids_must_not_look_like_secrets(cls, value: str) -> str:
        if SECRET_LIKE_ID_RE.search(value):
            raise ValueError("id field must not contain secret-like values")
        return value

    @field_validator("inputs")
    @classmethod
    def input_ids_must_be_unique(cls, value: list["LegacyAnalyzeInput"]) -> list["LegacyAnalyzeInput"]:
        if len({item.input_id for item in value}) != len(value):
            raise ValueError("input_id values must be unique")
        return value


class LegacyAnalyzeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_service: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
    ai_service_domain: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")
    page_url_origin: str = Field(min_length=1, max_length=255, pattern=r"^https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?$")
    extension_version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
    browser: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
    locale: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")


class LegacyAnalyzeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
    kind: Literal["text", "file_reference", "attachment_metadata", "unsupported_attachment"]
    source: Literal["composer", "converted_paste", "attached_file", "pasted_file", "pasted_image", "screenshot_image", "attachment_chip"]
    size_bytes: int = Field(ge=0, le=2_147_483_647)
    content_included: bool
    content: str | None = Field(default=None, max_length=1_048_576)
    file_ref: str | None = None
    temp_scope_id: str | None = None
    file_kind: FileKind | None = None
    mime: str | None = None
    extension: str | None = None
    size_bucket: SizeBucket | None = None
    metadata: dict[str, Any] | None = None
    content_unavailable_reason: Literal["oversized", "unsupported", "metadata_only", "unavailable"] | None = None
    limit_exceeded: Literal["MAX_ANALYZE_REQUEST_BYTES", "MAX_COMPOSER_TEXT_BYTES", "MAX_CONVERTED_PASTE_TEXT_BYTES"] | None = None

    @field_validator("input_id")
    @classmethod
    def id_must_not_look_like_secret(cls, value: str) -> str:
        if SECRET_LIKE_ID_RE.search(value):
            raise ValueError("input_id must not contain secret-like values")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "LegacyAnalyzeInput":
        if self.kind == "text":
            if self.file_ref is not None or self.temp_scope_id is not None or self.file_kind is not None:
                raise ValueError("text input forbids file reference fields")
            if self.source not in TEXT_SOURCES:
                raise ValueError("text input source must be composer or converted_paste")
            if self.content_included:
                if self.content is None or not self.content.strip():
                    raise ValueError("included text input must include non-blank content")
                content_size = len(self.content.encode("utf-8"))
                if content_size != self.size_bytes:
                    raise ValueError("size_bytes must equal UTF-8 content byte length")
                if content_size > TEXT_SOURCE_LIMITS[self.source]:
                    raise ValueError("included text input exceeds source byte limit")
                if self.content_unavailable_reason is not None or self.limit_exceeded is not None:
                    raise ValueError("included text input must not include unavailable metadata")
            else:
                if self.content is not None:
                    raise ValueError("content_unavailable text input must not include content")
                if self.content_unavailable_reason is None:
                    raise ValueError("content_unavailable text input must include a reason")
                if self.limit_exceeded is None and self.content_unavailable_reason == "oversized":
                    raise ValueError("oversized text input must include limit_exceeded")
        elif self.kind == "file_reference":
            if self.source not in {"attached_file", "pasted_file", "pasted_image", "screenshot_image"}:
                raise ValueError("file_reference has invalid source")
            if not self.file_ref or not re.fullmatch(r"fref_[A-Za-z0-9_-]{32,}", self.file_ref):
                raise ValueError("file_reference requires opaque file_ref")
            if not self.temp_scope_id or not SAFE_TEMP_SCOPE_ID_RE.fullmatch(self.temp_scope_id):
                raise ValueError("file_reference requires opaque temp_scope_id")
            _validate_file_reference_content_fields(self)
        elif self.kind == "attachment_metadata":
            if self.source != "attachment_chip":
                raise ValueError("attachment_metadata source must be attachment_chip")
            if self.content_included:
                raise ValueError("attachment_metadata content_included must be false")
            if self.content is not None:
                raise ValueError("attachment_metadata must not include content")
            if self.metadata is None:
                raise ValueError("attachment_metadata must include metadata")
            validate_safe_attachment_metadata(self.metadata)
        else:
            if self.source != "attachment_chip":
                raise ValueError("unsupported_attachment source must be attachment_chip")
            if self.content_included:
                raise ValueError("unsupported_attachment content_included must be false")
            if self.content is not None:
                raise ValueError("unsupported_attachment must not include content")
            if self.content_unavailable_reason is None:
                raise ValueError("unsupported_attachment must include a reason")
        return self


class AnalyzeInputItemV3(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_id: str
    kind: Literal["text", "file_reference", "attachment_metadata", "unsupported_attachment"]
    source: Literal["composer", "converted_paste", "pasted_file", "pasted_image", "screenshot_image", "attached_file", "attachment_chip"]
    content_included: bool
    content: str | None = None
    file_ref: str | None = None
    temp_scope_id: str | None = None
    file_kind: FileKind | None = None
    mime: str | None = None
    extension: str | None = None
    size_bucket: SizeBucket | None = None
    content_unavailable_reason: str | None = None


class AnalyzeRequestV3(BaseModel):
    request_id: str
    login_id: str
    schema_version: Literal["v3"] = ANALYZE_SCHEMA_VERSION
    extension_version: str | None = None
    inputs: list[AnalyzeInputItemV3]


class AdaptedAnalyzeRequest(BaseModel):
    v3_request: AnalyzeRequestV3
    legacy_view: LegacyAnalyzeRequest


def adapt_legacy_analyze_request(request: LegacyAnalyzeRequest, authenticated_login_id: str) -> AdaptedAnalyzeRequest:
    v3_inputs = []
    for item in request.inputs:
        v3_inputs.append(_adapt_input(item))
    return AdaptedAnalyzeRequest(v3_request=AnalyzeRequestV3(request_id=request.client_request_id, login_id=authenticated_login_id,
                                 extension_version=request.context.extension_version, inputs=v3_inputs),
                                 legacy_view=request)


def _adapt_input(item: LegacyAnalyzeInput) -> AnalyzeInputItemV3:
    metadata = item.metadata or {}
    return AnalyzeInputItemV3(input_id=item.input_id, kind=item.kind, source=item.source, content_included=item.content_included,
                              content=item.content, file_ref=item.file_ref, temp_scope_id=item.temp_scope_id, file_kind=item.file_kind,
                              mime=item.mime or _string(metadata.get("mime")), extension=item.extension or _string(metadata.get("extension")),
                              size_bucket=item.size_bucket or ("unknown" if item.kind not in {"text", "file_reference"} else None),
                              content_unavailable_reason=item.content_unavailable_reason or ("metadata_only" if item.kind == "attachment_metadata" else None))


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _validate_file_reference_content_fields(item: LegacyAnalyzeInput) -> None:
    if item.file_kind is None or item.content is not None or item.content_included:
        raise ValueError("file_reference requires file_kind and forbids content")


def validate_safe_attachment_metadata(metadata: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("attachment metadata must be JSON serializable") from exc
    if len(encoded) > 2_048:
        raise ValueError("attachment metadata is too large")
    if any(key.casefold() in FORBIDDEN_METADATA_KEYS for key in _metadata_keys(metadata)):
        raise ValueError("attachment metadata must not include original filename, path, or URL")


def _metadata_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [key for nested in value.values() for key in _metadata_keys(nested)]
    if isinstance(value, list):
        return [key for nested in value for key in _metadata_keys(nested)]
    return []


AnalyzeRequest = LegacyAnalyzeRequest
AnalyzeInput = LegacyAnalyzeInput
AnalyzeContext = LegacyAnalyzeContext
