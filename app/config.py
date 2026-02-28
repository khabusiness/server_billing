from __future__ import annotations

import base64
import json
from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppRegistryItem(BaseModel):
    package_name: str
    subscription_ids: set[str] = Field(default_factory=set)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = Field(default="billing-verify", alias="APP_NAME")
    environment: str = Field(default="production", alias="ENVIRONMENT")

    database_url: str = Field(alias="DATABASE_URL")
    google_service_account_json: str = Field(alias="GOOGLE_SERVICE_ACCOUNT_JSON")
    app_registry_json: str = Field(alias="APP_REGISTRY_JSON")
    client_keys_json: str | None = Field(default=None, alias="CLIENT_KEYS_JSON")
    purchase_token_hash_pepper: str = Field(alias="PURCHASE_TOKEN_HASH_PEPPER")

    cache_ttl_minutes: int = Field(default=10, alias="CACHE_TTL_MINUTES")
    google_timeout_seconds: int = Field(default=8, alias="GOOGLE_TIMEOUT_SECONDS")
    google_retries: int = Field(default=1, alias="GOOGLE_RETRIES")

    rate_limit_ip_per_minute: int = Field(default=60, alias="RATE_LIMIT_IP_PER_MINUTE")
    rate_limit_user_per_minute: int = Field(default=30, alias="RATE_LIMIT_USER_PER_MINUTE")
    rate_limit_token_per_minute: int = Field(default=10, alias="RATE_LIMIT_TOKEN_PER_MINUTE")

    store_raw_google_response: bool = Field(default=True, alias="STORE_RAW_GOOGLE_RESPONSE")
    auto_create_tables: bool = Field(default=False, alias="AUTO_CREATE_TABLES")

    @cached_property
    def app_registry(self) -> dict[str, AppRegistryItem]:
        try:
            raw = json.loads(self.app_registry_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("APP_REGISTRY_JSON is not valid JSON") from exc

        if not isinstance(raw, dict) or not raw:
            raise RuntimeError("APP_REGISTRY_JSON must be a non-empty object")

        parsed: dict[str, AppRegistryItem] = {}
        for app_id, cfg in raw.items():
            if not isinstance(cfg, dict):
                raise RuntimeError(f"Invalid config for app_id='{app_id}'")
            if "subscription_ids" not in cfg and "subscriptions" in cfg:
                cfg = {**cfg, "subscription_ids": cfg["subscriptions"]}
            try:
                parsed[app_id] = AppRegistryItem.model_validate(cfg)
            except ValidationError as exc:
                raise RuntimeError(f"Invalid app registry item for '{app_id}'") from exc
        return parsed

    @cached_property
    def client_keys(self) -> dict[str, list[str]]:
        if not self.client_keys_json:
            return {}
        try:
            raw = json.loads(self.client_keys_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CLIENT_KEYS_JSON is not valid JSON") from exc

        if not isinstance(raw, dict):
            raise RuntimeError("CLIENT_KEYS_JSON must be a JSON object")
        parsed: dict[str, list[str]] = {}
        for app_id, value in raw.items():
            key = str(app_id)
            if isinstance(value, str):
                parsed[key] = [value]
            elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                parsed[key] = [str(v) for v in value]
            else:
                raise RuntimeError(
                    "CLIENT_KEYS_JSON values must be string or list of strings"
                )
        return parsed

    @cached_property
    def google_service_account_info(self) -> dict[str, Any]:
        value = self.google_service_account_json.strip()
        if value.startswith("{"):
            return json.loads(value)

        path = Path(value)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

        try:
            decoded = base64.b64decode(value).decode("utf-8")
            if decoded.strip().startswith("{"):
                return json.loads(decoded)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON must be raw JSON, file path, or base64 JSON"
            ) from exc

        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON must be raw JSON, file path, or base64 JSON"
        )

    def get_app(self, app_id: str) -> AppRegistryItem | None:
        return self.app_registry.get(app_id)

    def get_client_keys(self, app_id: str) -> list[str]:
        if not self.client_keys:
            return []
        return self.client_keys.get(app_id) or self.client_keys.get("*") or self.client_keys.get(
            "shared", []
        )


settings = Settings()
