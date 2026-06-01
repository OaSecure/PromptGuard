import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
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


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login_id: Mapped[str] = mapped_column(String(80), nullable=False)
    login_id_normalized: Mapped[str] = mapped_column(String(80), nullable=False)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="USER")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash_algorithm: Mapped[str] = mapped_column(String(40), nullable=False)
    password_hash_params: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user")
    dashboard_sessions: Mapped[list["DashboardSession"]] = relationship(back_populates="user")

    __table_args__ = (
        CheckConstraint("role in ('ADMIN', 'USER')", name="ck_users_role"),
        CheckConstraint("status in ('ACTIVE', 'DISABLED')", name="ck_users_status"),
        UniqueConstraint("login_id_normalized", name="uq_users_login_id_normalized"),
        UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        Index("ix_users_login_id_normalized", "login_id_normalized"),
        Index("ix_users_role", "role"),
        Index("ix_users_status", "status"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    login_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
        Index("ix_refresh_tokens_login_expires", "login_id", "expires_at"),
    )


class DashboardSession(Base):
    __tablename__ = "dashboard_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    login_id: Mapped[str] = mapped_column(String(80), nullable=False)
    session_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="dashboard_sessions")

    __table_args__ = (
        UniqueConstraint("session_hash", name="uq_dashboard_sessions_session_hash"),
        Index("ix_dashboard_sessions_user_id", "user_id"),
        Index("ix_dashboard_sessions_login_expires", "login_id", "expires_at"),
        Index("ix_dashboard_sessions_expires_at", "expires_at"),
        Index("ix_dashboard_sessions_revoked_at", "revoked_at"),
    )
