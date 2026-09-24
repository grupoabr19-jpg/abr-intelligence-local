from __future__ import annotations

import hmac
import time
from hashlib import sha256

from fastapi import Cookie, Header, HTTPException, Response, status

from backend.api.config import get_api_settings


DASHBOARD_SESSION_COOKIE = "abr_dashboard_session"
DASHBOARD_SESSION_TTL_SECONDS = 60 * 60 * 12


def dashboard_password() -> str:
    settings = get_api_settings()
    return settings.abr_dashboard_password or settings.abr_api_key


def session_secret() -> str:
    settings = get_api_settings()
    return settings.abr_session_secret or settings.abr_api_key or settings.abr_dashboard_password


def create_dashboard_session() -> str:
    expires_at = int(time.time()) + DASHBOARD_SESSION_TTL_SECONDS
    secret = session_secret()
    signature = hmac.new(secret.encode("utf-8"), str(expires_at).encode("utf-8"), sha256).hexdigest()
    return f"{expires_at}.{signature}"


def valid_dashboard_session(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    expires_raw, signature = token.split(".", 1)
    if not expires_raw.isdigit():
        return False
    expires_at = int(expires_raw)
    if expires_at < int(time.time()):
        return False
    secret = session_secret()
    if not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), expires_raw.encode("utf-8"), sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def set_dashboard_session_cookie(response: Response, token: str | None = None) -> str:
    session_token = token or create_dashboard_session()
    response.set_cookie(
        key=DASHBOARD_SESSION_COOKIE,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=DASHBOARD_SESSION_TTL_SECONDS,
        path="/",
    )
    return session_token


def clear_dashboard_session_cookie(response: Response) -> None:
    response.delete_cookie(key=DASHBOARD_SESSION_COOKIE, path="/")


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_api_settings()
    if not settings.abr_api_key:
        return
    if x_api_key != settings.abr_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing x-api-key.",
        )


async def require_dashboard_read_key(
    x_api_key: str | None = Header(default=None),
    x_dashboard_session: str | None = Header(default=None),
    abr_dashboard_session: str | None = Cookie(default=None, alias=DASHBOARD_SESSION_COOKIE),
) -> None:
    settings = get_api_settings()
    allowed_keys = {key for key in (settings.abr_api_key, settings.abr_dashboard_read_key) if key}
    if valid_dashboard_session(abr_dashboard_session) or valid_dashboard_session(x_dashboard_session):
        return
    if not allowed_keys:
        return
    if x_api_key not in allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing dashboard read key.",
        )
