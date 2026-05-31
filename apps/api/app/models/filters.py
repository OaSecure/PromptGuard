import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.auth import TimestampMixin


class FilterRule(TimestampMixin, Base):
    __tablename__ = "filter_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detector_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    placeholder: Mapped[str | None] = mapped_column(String(80), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    editable_fields: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("origin in ('built_in', 'custom')", name="ck_filter_rules_origin"),
        CheckConstraint(
            "kind in ('detector', 'keyword', 'regex', 'context_rule')",
            name="ck_filter_rules_kind",
        ),
        CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_filter_rules_severity",
        ),
        CheckConstraint("action in ('ALLOW', 'WARN', 'MASK', 'BLOCK')", name="ck_filter_rules_action"),
        CheckConstraint("version > 0", name="ck_filter_rules_version_positive"),
        UniqueConstraint("detector_key", name="uq_filter_rules_detector_key"),
        Index("ix_filter_rules_enabled", "enabled"),
        Index("ix_filter_rules_origin_kind", "origin", "kind"),
        Index("ix_filter_rules_archived_at", "archived_at"),
    )
