from __future__ import annotations

from typing import Any

from fastapi import Response

from app.core.config import Settings


def _cookie_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": settings.cookie_path,
        "max_age": settings.refresh_token_ttl_seconds,
    }


def set_refresh_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    kwargs = _cookie_kwargs(settings)
    response.set_cookie(settings.refresh_cookie_name, raw_token, **kwargs)


def set_csrf_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    kwargs = _cookie_kwargs(settings)
    kwargs["httponly"] = False
    response.set_cookie(settings.csrf_cookie_name, raw_token, **kwargs)


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.refresh_cookie_name, path=settings.cookie_path)
    response.delete_cookie(settings.csrf_cookie_name, path=settings.cookie_path)
