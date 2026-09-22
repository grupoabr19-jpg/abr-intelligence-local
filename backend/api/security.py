from __future__ import annotations

from fastapi import Header, HTTPException, status

from backend.api.config import get_api_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_api_settings()
    if not settings.abr_api_key:
        return
    if x_api_key != settings.abr_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing x-api-key.",
        )
