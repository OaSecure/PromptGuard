import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FilterRule(TimestampMixin, Base):
    __tablename__ = "filter_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detector_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    placeholder: Mapped[str | None] = mapped_column(String(80), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    editable_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    versions: Mapped[list["FilterRuleVersion"]] = relationship(back_populates="filter_rule")

    __table_args__ = (
        CheckConstraint("source in ('built_in', 'custom')", name="ck_filter_rules_source"),
        CheckConstraint("kind in ('detector', 'keyword', 'regex', 'context_rule')", name="ck_filter_rules_kind"),
        CheckConstraint("severity in ('low', 'medium', 'high', 'critical')", name="ck_filter_rules_severity"),
        CheckConstraint("action in ('allow', 'warn', 'mask', 'block')", name="ck_filter_rules_action"),
        CheckConstraint("version > 0", name="ck_filter_rules_version_positive"),
        Index("ix_filter_rules_workspace_enabled", "workspace_id", "enabled"),
        Index("ix_filter_rules_workspace_source_kind", "workspace_id", "source", "kind"),
        Index("ix_filter_rules_archived_at", "archived_at"),
    )


class FilterRuleVersion(Base):
    __tablename__ = "filter_rule_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filter_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("filter_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    filter_rule: Mapped[FilterRule] = relationship(back_populates="versions")

    __table_args__ = (
        CheckConstraint("version > 0", name="ck_filter_rule_versions_version_positive"),
        CheckConstraint(
            "change_type in ('seed', 'create', 'update', 'enable', 'disable', 'archive')",
            name="ck_filter_rule_versions_change_type",
        ),
        Index("ix_filter_rule_versions_rule_version", "filter_rule_id", "version"),
        Index("ix_filter_rule_versions_workspace_created", "workspace_id", "created_at"),
    )
