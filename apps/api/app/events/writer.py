# -*- coding: utf-8 -*-
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import AnalysisEvent, EventDetection, EventInput, IdempotencyKey
from app.privacy.event_serializer import EventWriteProjection


class SqlAlchemyEventWriter:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def write(self, projection: EventWriteProjection) -> None:
        self._session.add(AnalysisEvent(**projection.event.model_dump()))
        for item in projection.inputs:
            self._session.add(EventInput(**item.model_dump()))
        for detection in projection.detections:
            values = detection.model_dump()
            values["safe_evidence"] = detection.safe_evidence.model_dump(exclude_none=True, exclude_defaults=True)
            self._session.add(EventDetection(**values))
        self._session.add(IdempotencyKey(**projection.idempotency.model_dump()))
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise


async def load_idempotency_event_id(session: AsyncSession, login_id: str, client_request_id: str):
    result = await session.execute(
        select(IdempotencyKey.event_id).where(
            IdempotencyKey.login_id == login_id,
            IdempotencyKey.client_request_id == client_request_id,
        )
    )
    return result.scalars().first()
