from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


STATUS_VALUES = (
    "TRIAL_ACTIVE",
    "PAID_ACTIVE",
    "ON_HOLD",
    "EXPIRED",
    "CANCELED_ACTIVE",
    "UNKNOWN",
)


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(min_length=2, max_length=64)
    package_name: str = Field(min_length=3, max_length=255)
    subscription_id: str = Field(min_length=1, max_length=255)
    purchase_token: str = Field(min_length=21, max_length=2048)
    user_id: str = Field(min_length=8, max_length=128)
    force: bool = False

    @field_validator("app_id")
    @classmethod
    def validate_app_id(cls, value: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.-]+$", value):
            raise ValueError("app_id has invalid characters")
        return value

    @field_validator("package_name")
    @classmethod
    def validate_package(cls, value: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.]+$", value):
            raise ValueError("package_name has invalid characters")
        return value

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, value: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.:-]+$", value):
            raise ValueError("user_id has invalid characters")
        return value


class VerifyResponse(BaseModel):
    active: bool
    status: Literal[
        "TRIAL_ACTIVE",
        "PAID_ACTIVE",
        "ON_HOLD",
        "EXPIRED",
        "CANCELED_ACTIVE",
        "UNKNOWN",
    ]
    is_trial: bool
    auto_renewing: bool
    expiry_time_ms: int
    app_id: str
    package_name: str
    subscription_id: str


class ErrorResponse(BaseModel):
    error: str
    message: str
