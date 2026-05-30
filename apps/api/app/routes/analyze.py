import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.core.tokens import utc_now
from app.models.auth import User
from app.routes.auth import require_active_user

router = APIRouter(prefix="/prompts", tags=["prompts"])

MAX_PROMPT_LENGTH = 20_000
MAX_CONTEXT_JSON_LENGTH = 4_096


class AnalyzeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    context: dict[str, Any] = Field(default_factory=dict)
    filter_config_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    client_request_id: uuid.UUID | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value

    @field_validator("context")
    @classmethod
    def context_must_be_bounded_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("context must be JSON serializable") from exc

        if len(encoded) > MAX_CONTEXT_JSON_LENGTH:
            raise ValueError("context is too large")
        return value


class WorkspaceContext(BaseModel):
    source: Literal["authenticated_user"]
    user_id: uuid.UUID


class AnalyzeResponse(BaseModel):
    request_id: uuid.UUID
    status: Literal["accepted"]
    action: Literal["ALLOW"]
    checked_at: datetime
    prompt_length: int
    client_request_id: uuid.UUID | None
    filter_config_version: str | None
    workspace_context: WorkspaceContext


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_prompt(
    payload: AnalyzeRequest,
    current_user: User = Depends(require_active_user),
) -> AnalyzeResponse:
    return AnalyzeResponse(
        request_id=uuid.uuid4(),
        status="accepted",
        action="ALLOW",
        checked_at=utc_now(),
        prompt_length=len(payload.prompt),
        client_request_id=payload.client_request_id,
        filter_config_version=payload.filter_config_version,
        workspace_context=WorkspaceContext(source="authenticated_user", user_id=current_user.id),
    )
