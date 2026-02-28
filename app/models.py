from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BIGINT, JSON, Boolean, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SubscriptionVerification(Base):
    __tablename__ = "subscription_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    purchase_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    expiry_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    is_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_renewing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_google_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_sub_ver_app_user", "app_id", "user_id"),
        Index("idx_sub_ver_token_hash", "purchase_token_hash"),
        Index("idx_sub_ver_expiry_time_ms", "expiry_time_ms"),
    )


class Entitlement(Base):
    __tablename__ = "entitlements"

    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    purchase_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expiry_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    last_verified_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("app_id", "user_id", name="uq_entitlements_app_user"),
        Index("idx_entitlements_token_hash", "purchase_token_hash"),
    )
