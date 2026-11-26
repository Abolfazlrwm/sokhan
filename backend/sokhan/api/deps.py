"""Shared FastAPI dependencies: database session, current user and admin key."""

import secrets

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from sokhan.auth import token_hash
from sokhan.config import get_settings
from sokhan.db import get_db
from sokhan.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    user = session.scalar(
        select(User).where(User.token_hash == token_hash(credentials.credentials))
    )
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
