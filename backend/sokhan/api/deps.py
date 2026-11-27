"""Shared FastAPI dependencies: database session, current user and admin key.

A request authenticates in one of two ways:

- `Authorization: Bearer <token>`: API clients, the bot and scripts. A
  browser never attaches this header on its own, so no CSRF check applies.
- the httpOnly session cookie set at sign-in: the web dashboard. Browsers
  send it automatically, so every unsafe method must also carry the
  matching X-CSRF-Token header (see `sokhan.auth.csrf_token_for`).
"""

import secrets

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from sokhan.auth import csrf_token_for, token_hash
from sokhan.config import get_settings
from sokhan.db import get_db
from sokhan.models import User

_bearer = HTTPBearer(auto_error=False)

SESSION_COOKIE = "sokhan_session"
CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_request_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """The caller's raw token, from the bearer header or the session cookie.

    Cookie-authenticated unsafe requests must send the CSRF token; a
    missing or wrong one is a 403 before the token is even looked up.
    """
    if credentials is not None and credentials.credentials:
        return credentials.credentials
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    if request.method not in _SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not secrets.compare_digest(sent, csrf_token_for(token)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or invalid CSRF token")
    return token


def get_current_user(
    token: str = Depends(get_request_token),
    session: Session = Depends(get_db),
) -> User:
    user = session.scalar(select(User).where(User.token_hash == token_hash(token)))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return user


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """Guard the admin routes behind the shared X-Admin-Key secret.

    The comparison is constant-time. An empty ADMIN_API_KEY disables the
    whole admin surface (503) so an operator can never leave it open by
    accident; a wrong key is a plain 403.
    """
    settings = get_settings()
    if not settings.admin_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "admin API disabled: set ADMIN_API_KEY to enable it",
        )
    if x_admin_key is None or not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid admin key")


def require_bot(x_bot_secret: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.bot_api_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "telegram login disabled: set BOT_API_SECRET on the API and the bot",
        )
    if x_bot_secret is None or not secrets.compare_digest(x_bot_secret, settings.bot_api_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid bot secret")
