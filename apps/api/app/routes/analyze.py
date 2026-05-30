import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.detectors.pii import Detection, detect_pii
from app.masking.placeholder import apply_placeholders
from app.models.auth import User
from app.routes.auth import require_active_user

router = APIRouter(prefix="/prompts", tags=["prompts"])

MAX_PROMPT_LENGTH = 20_000

DecisionAction = Literal["Allow", "Warn", "Mask", "Block"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class PromptPayload(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    input_method: str = Field(min_length=1, max_length=80)
    content_length: int = Field(ge=1, le=MAX_PROMPT_LENGTH)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt text must not be blank")
        return value

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


class PolicyRef(BaseModel):
    version: str = Field(min_length=1, max_length=120)


class AnalyzeRequest(BaseModel):
    prompt: PromptPayload
    context: AnalyzeContext
    policy: PolicyRef
    client_request_id: str = Field(min_length=1, max_length=120)


class Decision(BaseModel):
    risk_score: int
    risk_level: RiskLevel
    action: DecisionAction
    user_message: str
    allow_original_send: bool


class DetectionSummary(BaseModel):
    type: str
    label: str
    count: int
    severity: Literal["low", "medium", "high", "critical"]
    confidence: float
    source: Literal["prompt"]


class PolicyStatus(BaseModel):
    version: str
    latest_version: str


class AnalyzeResponse(BaseModel):
    event_id: str
    request_id: str
    decision: Decision
    detections: list[DetectionSummary]
    policy: PolicyStatus
    partial_result: bool = False
    masked_prompt: str | None = None


def risk_score_for(detections: list[Detection]) -> int:
    if any(item.detector_key in {"RRN", "CARD"} for item in detections):
        return 90
    if any(item.detector_key in {"EMAIL", "PHONE"} for item in detections):
        return 70
    return 1


def action_for(score: int, detections: list[Detection]) -> DecisionAction:
    if any(item.detector_key in {"RRN", "CARD"} for item in detections):
        return "Block"
    if score >= 60:
        return "Mask"
    return "Allow"


def risk_level_for(score: int) -> RiskLevel:
    if score >= 85:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def user_message_for(action: DecisionAction) -> str:
    if action == "Block":
        return "민감도가 높은 정보가 감지되어 원문 전송을 차단했습니다."
    if action == "Mask":
        return "민감정보를 placeholder로 치환했습니다. 마스킹된 내용을 확인한 뒤 전송하세요."
    return "전송 가능한 요청입니다."


def detection_summary(detection: Detection) -> DetectionSummary:
    severity: Literal["low", "medium", "high", "critical"] = (
        "critical" if detection.detector_key in {"RRN", "CARD"} else "high"
    )
    return DetectionSummary(
        type=detection.detector_key,
        label=detection.category,
        count=1,
        severity=severity,
        confidence=1.0,
        source="prompt",
    )


def summarize_detections(detections: list[Detection]) -> list[DetectionSummary]:
    grouped: dict[tuple[str, str, str], DetectionSummary] = {}
    for detection in detections:
        summary = detection_summary(detection)
        key = (summary.type, summary.label, summary.severity)
        if key in grouped:
            grouped[key].count += 1
        else:
            grouped[key] = summary
    return list(grouped.values())


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
        request_id=f"req_{uuid.uuid4().hex}",
        decision=Decision(
            risk_score=score,
            risk_level=risk_level_for(score),
            action=action,
            user_message=user_message_for(action),
            allow_original_send=action == "Allow",
        ),
        detections=summarize_detections(detections),
        policy=PolicyStatus(version=payload.policy.version, latest_version=payload.policy.version),
        partial_result=False,
        masked_prompt=masked_prompt,
    )
