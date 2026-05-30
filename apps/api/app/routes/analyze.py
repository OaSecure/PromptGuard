import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.detectors.pii import Detection, detect_pii
from app.masking.placeholder import apply_placeholders
from app.models.auth import User
from app.routes.auth import require_active_user

router = APIRouter(prefix="/prompts", tags=["analyze"])

AnalyzeAction = Literal["Allow", "Warn", "Mask", "Block"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class PromptPayload(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    input_method: str = Field(min_length=1, max_length=80)
    content_length: int = Field(ge=1, le=20000)

    @field_validator("content_length")
    @classmethod
    def content_length_matches_text(cls, value: int, info) -> int:
        text = info.data.get("text")
        if isinstance(text, str) and value != len(text):
            raise ValueError("content_length must match prompt text length")
        return value


class AnalyzeContext(BaseModel):
    ai_service: str = Field(min_length=1, max_length=80)
    ai_service_domain: str = Field(min_length=1, max_length=255)
    page_url_origin: str = Field(min_length=1, max_length=255)
    extension_version: str = Field(min_length=1, max_length=80)
    browser: str = Field(min_length=1, max_length=80)
    locale: str = Field(min_length=1, max_length=20)


class AnalyzeRequest(BaseModel):
    prompt: PromptPayload
    context: AnalyzeContext
    filter_config_version: str = Field(min_length=1, max_length=120)
    client_request_id: str = Field(min_length=1, max_length=120)


class DetectionResponse(BaseModel):
    detector_key: str
    category: str
    start: int
    end: int
    placeholder: str
    value_length: int


class AnalyzeResponse(BaseModel):
    event_id: str
    request_id: str
    risk_score: int
    risk_level: RiskLevel
    action: AnalyzeAction
    user_message: str
    allow_original_send: bool
    requires_justification: bool
    detections: list[DetectionResponse]
    filter_config_version: str
    masked_prompt: str | None = None
    partial_result: bool = False


def detection_response(detection: Detection) -> DetectionResponse:
    return DetectionResponse(
        detector_key=detection.detector_key,
        category=detection.category,
        start=detection.start,
        end=detection.end,
        placeholder=detection.placeholder,
        value_length=detection.value_length,
    )


def risk_score_for(detections: list[Detection]) -> int:
    if any(item.detector_key in {"RRN", "CARD"} for item in detections):
        return 90
    if any(item.detector_key in {"EMAIL", "PHONE"} for item in detections):
        return 70
    return 0


def action_for(score: int, detections: list[Detection]) -> AnalyzeAction:
    if any(item.detector_key in {"RRN", "CARD"} for item in detections):
        return "Block"
    if score >= 60:
        return "Mask"
    return "Allow"


def risk_level_for(score: int) -> RiskLevel:
    if score >= 85:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def user_message_for(action: AnalyzeAction) -> str:
    if action == "Block":
        return "민감도가 높은 정보가 감지되어 원문 전송을 차단했습니다."
    if action == "Mask":
        return "민감정보를 placeholder로 치환했습니다. 마스킹된 내용을 확인한 뒤 전송하세요."
    return "전송 가능한 요청입니다."


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_prompt(
    payload: AnalyzeRequest,
    _current_user: User = Depends(require_active_user),
) -> AnalyzeResponse:
    detections = detect_pii(payload.prompt.text)
    score = risk_score_for(detections)
    action = action_for(score, detections)
    masked_prompt = None

    if action == "Mask":
        masked_prompt = apply_placeholders(payload.prompt.text, detections).text

    return AnalyzeResponse(
        event_id=f"evt_{uuid.uuid4().hex}",
        request_id=payload.client_request_id,
        risk_score=score,
        risk_level=risk_level_for(score),
        action=action,
        user_message=user_message_for(action),
        allow_original_send=action == "Allow",
        requires_justification=action == "Warn",
        detections=[detection_response(item) for item in detections],
        filter_config_version=payload.filter_config_version,
        masked_prompt=masked_prompt,
    )
