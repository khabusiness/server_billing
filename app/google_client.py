from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_httplib2 import AuthorizedHttp


ANDROID_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"


class GoogleVerifyError(Exception):
    def __init__(self, message: str, status_code: int, retryable: bool) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


@dataclass
class GoogleVerifyResult:
    active: bool
    status: str
    is_trial: bool
    auto_renewing: bool
    expiry_time_ms: int
    raw_response: dict[str, Any]


def _to_unix_ms(rfc3339: str | None) -> int:
    if not rfc3339:
        return 0
    value = rfc3339.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return 0
    return int(dt.timestamp() * 1000)


def _detect_trial(line_item: dict[str, Any]) -> bool:
    offer_details = line_item.get("offerDetails") or {}
    offer_id = str(offer_details.get("offerId") or "").lower()
    tags = [str(tag).lower() for tag in (offer_details.get("offerTags") or [])]
    return "trial" in offer_id or "intro" in offer_id or any(
        ("trial" in tag or "intro" in tag) for tag in tags
    )


class GooglePlayVerifier:
    def __init__(self, service_account_info: dict[str, Any], timeout_seconds: int = 8) -> None:
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=[ANDROID_PUBLISHER_SCOPE]
        )
        http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=timeout_seconds))
        self.service = build("androidpublisher", "v3", http=http, cache_discovery=False)

    def verify(
        self,
        package_name: str,
        subscription_id: str,
        purchase_token: str,
        now_ms: int,
        retries: int = 1,
    ) -> GoogleVerifyResult:
        try:
            response = (
                self.service.purchases()
                .subscriptionsv2()
                .get(packageName=package_name, token=purchase_token)
                .execute(num_retries=retries)
            )
        except HttpError as exc:
            status = getattr(exc.resp, "status", 500) or 500
            body = {"error": str(exc)}
            if status in (400, 404, 410):
                fallback_status = "EXPIRED" if status in (404, 410) else "UNKNOWN"
                return GoogleVerifyResult(
                    active=False,
                    status=fallback_status,
                    is_trial=False,
                    auto_renewing=False,
                    expiry_time_ms=0,
                    raw_response=body,
                )
            if status in (429, 500, 502, 503, 504):
                raise GoogleVerifyError("Google API unavailable", status_code=503, retryable=True) from exc
            raise GoogleVerifyError("Google API rejected request", status_code=502, retryable=False) from exc
        except TimeoutError as exc:
            raise GoogleVerifyError("Google API timeout", status_code=503, retryable=True) from exc

        line_items = response.get("lineItems") or []
        matched = next((x for x in line_items if x.get("productId") == subscription_id), None)

        if matched is None:
            return GoogleVerifyResult(
                active=False,
                status="UNKNOWN",
                is_trial=False,
                auto_renewing=False,
                expiry_time_ms=0,
                raw_response=response,
            )

        expiry_ms = _to_unix_ms(matched.get("expiryTime"))
        auto_renewing = bool((matched.get("autoRenewingPlan") or {}).get("autoRenewEnabled"))
        is_trial = _detect_trial(matched)
        state = str(response.get("subscriptionState") or "")
        active = now_ms < expiry_ms

        if state == "SUBSCRIPTION_STATE_ON_HOLD" or state == "SUBSCRIPTION_STATE_IN_GRACE_PERIOD":
            status = "ON_HOLD"
        elif state == "SUBSCRIPTION_STATE_CANCELED" and active:
            status = "CANCELED_ACTIVE"
        elif state == "SUBSCRIPTION_STATE_EXPIRED" or not active:
            status = "EXPIRED"
        elif active and is_trial:
            status = "TRIAL_ACTIVE"
        elif active:
            status = "PAID_ACTIVE"
        else:
            status = "UNKNOWN"

        return GoogleVerifyResult(
            active=active,
            status=status,
            is_trial=is_trial,
            auto_renewing=auto_renewing,
            expiry_time_ms=expiry_ms,
            raw_response=response,
        )
