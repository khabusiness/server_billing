from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import Entitlement, SubscriptionVerification


def get_recent_cached_verification(
    db: Session, app_id: str, purchase_token_hash: str, cache_ttl_minutes: int
) -> SubscriptionVerification | None:
    edge = datetime.now(timezone.utc) - timedelta(minutes=cache_ttl_minutes)
    stmt = (
        select(SubscriptionVerification)
        .where(
            SubscriptionVerification.app_id == app_id,
            SubscriptionVerification.purchase_token_hash == purchase_token_hash,
            SubscriptionVerification.created_at >= edge,
        )
        .order_by(desc(SubscriptionVerification.created_at))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def save_verification(
    db: Session,
    app_id: str,
    package_name: str,
    subscription_id: str,
    user_id: str,
    purchase_token_hash: str,
    active: bool,
    status: str,
    expiry_time_ms: int,
    is_trial: bool,
    auto_renewing: bool,
    raw_google_response: dict[str, Any] | None,
    now_ms: int,
) -> None:
    verification = SubscriptionVerification(
        app_id=app_id,
        package_name=package_name,
        subscription_id=subscription_id,
        user_id=user_id,
        purchase_token_hash=purchase_token_hash,
        active=active,
        status=status,
        expiry_time_ms=expiry_time_ms,
        is_trial=is_trial,
        auto_renewing=auto_renewing,
        raw_google_response=raw_google_response,
    )
    db.add(verification)

    entitlement_upsert = insert(Entitlement).values(
        app_id=app_id,
        user_id=user_id,
        purchase_token_hash=purchase_token_hash,
        status=status,
        active=active,
        expiry_time_ms=expiry_time_ms,
        last_verified_ms=now_ms,
    )
    db.execute(
        entitlement_upsert.on_conflict_do_update(
            index_elements=["app_id", "user_id"],
            set_={
                "purchase_token_hash": purchase_token_hash,
                "status": status,
                "active": active,
                "expiry_time_ms": expiry_time_ms,
                "last_verified_ms": now_ms,
                "updated_at": datetime.now(timezone.utc),
            },
        )
    )
