from typing import Protocol

from app.domain.types.storage import EventWriteRequest, EventWriteResult


class PrivacyAllowlistSerializerPort(Protocol):
    def serialize(self, request: EventWriteRequest) -> dict[str, object]: ...
class EventWriterPort(Protocol):
    def write(self, request: EventWriteRequest) -> EventWriteResult: ...
