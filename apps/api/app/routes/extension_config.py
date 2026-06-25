from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings, get_settings
from app.models.auth import User
from app.routes.auth import require_active_user

router = APIRouter(prefix="/config", tags=["extension-config"])


class ExtensionSelectors(BaseModel):
    """Selectors the extension uses to find protected ChatGPT UI controls."""

    input: list[str]
    send_button: list[str]
    file_input: list[str]
    drop_zone: list[str]
    attachment_chip: list[str]


class AiServiceConfig(BaseModel):
    """Per-service extension detection config."""

    service: Literal["CHATGPT"]
    domains: list[str]
    selectors: ExtensionSelectors


class FileUploadPolicy(BaseModel):
    """File upload limits exposed to the extension without raw file data."""

    enabled: bool
    max_file_size_bytes: int
    max_total_size_bytes: int
    max_file_count: int
    allowed_extensions: list[str]
    excluded_extensions: list[str]


class RequestTimeouts(BaseModel):
    """Request-specific timeouts consumed by the extension."""

    config_request_ms: int
    analyze_request_ms: int


class InputLimits(BaseModel):
    """Byte limits consumed by the extension preflight builders."""

    composer_text_bytes: int
    converted_paste_text_bytes: int
    file_text_scan_bytes: int
    analyze_request_bytes: int


class ExtensionConfigResponse(BaseModel):
    """Remote config shape consumed by the MV3 extension."""

    model_config = ConfigDict(extra="forbid")

    api_base_url: str
    filter_config_revision: str
    request_timeouts: RequestTimeouts
    input_limits: InputLimits
    attachment_policy: FileUploadPolicy
    # Legacy compatibility fields retained until older extension builds age out.
    policy_version: str
    timeout_ms: int
    ai_service_configs: list[AiServiceConfig]
    file_upload: FileUploadPolicy


@router.get("/extension", response_model=ExtensionConfigResponse)
async def extension_config(
    _current_user: User = Depends(require_active_user),
    settings: Settings = Depends(get_settings),
) -> ExtensionConfigResponse:
    """Return remote extension config for authenticated extension clients."""

    attachment_policy = FileUploadPolicy(
        enabled=True,
        max_file_size_bytes=settings.temp_file_max_bytes,
        max_total_size_bytes=settings.temp_file_max_bytes * 3,
        max_file_count=5,
        allowed_extensions=[
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".log",
            ".env",
            ".ini",
            ".conf",
            ".sql",
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".pdf",
            ".docx",
            ".xlsx",
            ".pptx",
            ".png",
            ".jpg",
            ".jpeg",
        ],
        excluded_extensions=[".zip"],
    )
    return ExtensionConfigResponse(
        api_base_url=settings.api_public_url,
        filter_config_revision="cfg_default",
        request_timeouts=RequestTimeouts(
            config_request_ms=5000,
            analyze_request_ms=settings.ml_inference_queue_timeout_ms,
        ),
        input_limits=InputLimits(
            composer_text_bytes=262_144,
            converted_paste_text_bytes=1_048_576,
            file_text_scan_bytes=1_048_576,
            analyze_request_bytes=2_097_152,
        ),
        attachment_policy=attachment_policy,
        policy_version="cfg_default",
        timeout_ms=settings.ml_inference_queue_timeout_ms,
        ai_service_configs=[
            AiServiceConfig(
                service="CHATGPT",
                domains=["chatgpt.com", "chat.openai.com"],
                selectors=ExtensionSelectors(
                    input=["textarea", "[contenteditable='true']"],
                    send_button=[
                        "button[data-testid='send-button']",
                        "button[data-testid='composer-send-button']",
                        "button[data-testid*='send']",
                        "button[aria-label='Send message']",
                        "button[aria-label='Send prompt']",
                        "button[aria-label='Send']",
                        "button[aria-label*='보내기']",
                    ],
                    file_input=["input[type='file']"],
                    drop_zone=["body"],
                    attachment_chip=[
                        "[data-promptguard-attachment-chip]",
                        "[data-testid='attachment-chip']",
                        "[data-testid='attachment-item']",
                    ],
                ),
            )
        ],
        file_upload=attachment_policy,
    )
