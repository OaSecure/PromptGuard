from pydantic import BaseModel, Field


class EventWriteRequest(BaseModel):
    event_id: str
    request_id: str
    action: str
    reason_codes: list[str] = Field(default_factory=list)
    input_count: int


class EventWriteResult(BaseModel):
    event_id: str
    written: bool
