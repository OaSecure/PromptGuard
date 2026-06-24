import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.auth import TimestampMixin


class PolicySettings(TimestampMixin, Base):
    __tablename__ = "policy_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    settings_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    context_classifier_action: Mapped[str] = mapped_column(String(20), nullable=False, default="WARN")
    content_not_scanned_action: Mapped[str] = mapped_column(String(20), nullable=False, default="WARN")
    parser_or_ocr_failure_action: Mapped[str] = mapped_column(String(20), nullable=False, default="WARN")
    empty_input_action: Mapped[str] = mapped_column(String(20), nullable=False, default="ALLOW")
    unsupported_mask_fallback_action: Mapped[str] = mapped_column(String(20), nullable=False, default="BLOCK")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("settings_key", name="uq_policy_settings_key"),
        CheckConstraint("settings_key = 'default'", name="ck_policy_settings_singleton_key"),
        CheckConstraint(
            "context_classifier_action in ('ALLOW', 'WARN', 'BLOCK')",
            name="ck_policy_settings_context_classifier_action",
        ),
        CheckConstraint(
            "content_not_scanned_action in ('ALLOW', 'WARN', 'BLOCK')",
            name="ck_policy_settings_content_not_scanned_action",
        ),
        CheckConstraint(
            "parser_or_ocr_failure_action in ('ALLOW', 'WARN', 'BLOCK')",
            name="ck_policy_settings_parser_or_ocr_failure_action",
        ),
        CheckConstraint(
            "empty_input_action in ('ALLOW', 'WARN', 'BLOCK')",
            name="ck_policy_settings_empty_input_action",
        ),
        CheckConstraint(
            "unsupported_mask_fallback_action in ('WARN', 'BLOCK')",
            name="ck_policy_settings_unsupported_mask_fallback_action",
        ),
        CheckConstraint("version > 0", name="ck_policy_settings_version_positive"),
        Index("ix_policy_settings_key", "settings_key"),
    )
