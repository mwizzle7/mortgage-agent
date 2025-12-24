from __future__ import annotations

from fastapi import Header, HTTPException, Request

from app.core.config import settings


def verify_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    if not settings.admin_token_enabled:
        return
    expected = settings.admin_token
    if not expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"
