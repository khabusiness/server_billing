from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .google_client import GooglePlayVerifier, GoogleVerifyError
from .rate_limit import SlidingWindowRateLimiter
from .repository import get_recent_cached_verification, save_verification
from .schemas import ErrorResponse, VerifyRequest, VerifyResponse
from .security import hash_purchase_token, verify_client_key

# Needed so SQLAlchemy sees model metadata before create_all.
from . import models  # noqa: F401


logger = logging.getLogger("billing")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def _log_event(event: str, **fields: object) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False))


def _error_response(status_code: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "message": message})


rate_limiter = SlidingWindowRateLimiter(window_seconds=60)
google_verifier: GooglePlayVerifier | None = None

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def startup() -> None:
    global google_verifier
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    google_verifier = GooglePlayVerifier(
        service_account_info=settings.google_service_account_info,
        timeout_seconds=settings.google_timeout_seconds,
    )


@app.middleware("http")
async def add_request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_event(
            "http_request_error",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            latency_ms=latency_ms,
        )
        raise
    latency_ms = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    _log_event(
        "http_request",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    message = "; ".join(error.get("msg", "invalid value") for error in exc.errors())
    _log_event("invalid_request", request_id=request.state.request_id, message=message)
    return _error_response(400, "INVALID_REQUEST", message)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        error = str(exc.detail.get("error", "HTTP_ERROR"))
        message = str(exc.detail.get("message", "Request failed"))
    else:
        error = "HTTP_ERROR"
        message = str(exc.detail)
    _log_event(
        "http_exception",
        request_id=request.state.request_id,
        status_code=exc.status_code,
        error=error,
        message=message,
    )
    return _error_response(exc.status_code, error, message)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post(
    "/v1/billing/android/verify",
    response_model=VerifyResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def verify_android(
    payload: VerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_client_key: str | None = Header(default=None, alias="X-Client-Key"),
) -> VerifyResponse:
    request_id = request.state.request_id
    app_cfg = settings.get_app(payload.app_id)
    if app_cfg is None:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN_APP", "message": "Unknown app_id"},
        )
    if payload.package_name != app_cfg.package_name:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN_APP", "message": "package_name does not match app_id"},
        )
    if payload.subscription_id not in app_cfg.subscription_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_REQUEST", "message": "subscription_id is not allowed for app_id"},
        )

    configured_keys = settings.get_client_keys(payload.app_id)
    if configured_keys:
        if not x_client_key:
            raise HTTPException(
                status_code=401,
                detail={"error": "UNAUTHORIZED", "message": "Missing or invalid X-Client-Key"},
            )
        if not any(verify_client_key(x_client_key, value) for value in configured_keys):
            raise HTTPException(
                status_code=401,
                detail={"error": "UNAUTHORIZED", "message": "Missing or invalid X-Client-Key"},
            )

    purchase_token_hash = hash_purchase_token(
        payload.purchase_token,
        settings.purchase_token_hash_pepper,
    )
    ip = request.client.host if request.client and request.client.host else "unknown"

    if not rate_limiter.allow(f"ip:{ip}", settings.rate_limit_ip_per_minute):
        raise HTTPException(
            status_code=429,
            detail={"error": "RATE_LIMITED", "message": "Too many requests from IP"},
        )
    if not rate_limiter.allow(f"user:{payload.app_id}:{payload.user_id}", settings.rate_limit_user_per_minute):
        raise HTTPException(
            status_code=429,
            detail={"error": "RATE_LIMITED", "message": "Too many requests for user_id"},
        )
    if not rate_limiter.allow(
        f"token:{payload.app_id}:{purchase_token_hash}",
        settings.rate_limit_token_per_minute,
    ):
        raise HTTPException(
            status_code=429,
            detail={"error": "RATE_LIMITED", "message": "Too many requests for purchase_token"},
        )

    if not payload.force:
        cached = get_recent_cached_verification(
            db=db,
            app_id=payload.app_id,
            purchase_token_hash=purchase_token_hash,
            cache_ttl_minutes=settings.cache_ttl_minutes,
        )
        if cached is not None:
            _log_event(
                "verify_cache_hit",
                request_id=request_id,
                app_id=payload.app_id,
                status=cached.status,
                token_hash=purchase_token_hash[:12],
            )
            return VerifyResponse(
                active=cached.active,
                status=cached.status,
                is_trial=cached.is_trial,
                auto_renewing=cached.auto_renewing,
                expiry_time_ms=cached.expiry_time_ms,
                app_id=payload.app_id,
                package_name=payload.package_name,
                subscription_id=payload.subscription_id,
            )

    verifier = google_verifier
    if verifier is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "GOOGLE_API_UNAVAILABLE", "message": "Verifier is not initialized"},
        )

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        result = verifier.verify(
            package_name=payload.package_name,
            subscription_id=payload.subscription_id,
            purchase_token=payload.purchase_token,
            now_ms=now_ms,
            retries=settings.google_retries,
        )
    except GoogleVerifyError as exc:
        error_code = "GOOGLE_API_UNAVAILABLE" if exc.retryable else "GOOGLE_API_ERROR"
        raise HTTPException(status_code=exc.status_code, detail={"error": error_code, "message": str(exc)}) from exc

    try:
        save_verification(
            db=db,
            app_id=payload.app_id,
            package_name=payload.package_name,
            subscription_id=payload.subscription_id,
            user_id=payload.user_id,
            purchase_token_hash=purchase_token_hash,
            active=result.active,
            status=result.status,
            expiry_time_ms=result.expiry_time_ms,
            is_trial=result.is_trial,
            auto_renewing=result.auto_renewing,
            raw_google_response=result.raw_response if settings.store_raw_google_response else None,
            now_ms=now_ms,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _log_event("db_write_failed", request_id=request_id, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={"error": "DATABASE_ERROR", "message": "Failed to persist verification"},
        ) from exc

    _log_event(
        "verify_success",
        request_id=request_id,
        app_id=payload.app_id,
        user_id=payload.user_id,
        status=result.status,
        active=result.active,
        token_hash=purchase_token_hash[:12],
    )

    return VerifyResponse(
        active=result.active,
        status=result.status,
        is_trial=result.is_trial,
        auto_renewing=result.auto_renewing,
        expiry_time_ms=result.expiry_time_ms,
        app_id=payload.app_id,
        package_name=payload.package_name,
        subscription_id=payload.subscription_id,
    )
