"""Registration and login endpoints.

Deliberately lightweight for v1:

- email + password (scrypt-hashed) for the web dashboard; the API token is
  shown once and stored server-side only as a SHA-256 hash
- POST /auth/telegram lets the bot create or resume an account per Telegram id
- POST /auth/token-login lets a user paste the connect code shown by the bot
  to link their browser session
"""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from sokhan.auth import generate_token, hash_password, token_hash, verify_password
from sokhan.db import get_db
from sokhan.models import User
from sokhan.schemas import AuthResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LENGTH = 8


class Credentials(BaseModel):
    email: str
    password: str


class TelegramLogin(BaseModel):
    telegram_id: int
    username: str | None = None


class TokenLogin(BaseModel):
    api_token: str


def _validate_credentials(email: str, password: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_PATTERN.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email address")
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"password too short (minimum {_MIN_PASSWORD_LENGTH} characters)",
        )
    return email


@router.post("/register", response_model=AuthResponse)
def register(payload: Credentials, session: Session = Depends(get_db)) -> AuthResponse:
    email = _validate_credentials(payload.email, payload.password)
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    token = generate_token()
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        token_hash=token_hash(token),
    )
    session.add(user)
    session.commit()
    return AuthResponse(id=user.id, email=user.email, api_token=token)


@router.post("/login", response_model=AuthResponse)
def login(payload: Credentials, session: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    token = generate_token()
    user.token_hash = token_hash(token)
    session.commit()
    return AuthResponse(id=user.id, email=user.email, api_token=token)


@router.post("/token-login", response_model=AuthResponse)
def token_login(payload: TokenLogin, session: Session = Depends(get_db)) -> AuthResponse:
    user = session.scalar(select(User).where(User.token_hash == token_hash(payload.api_token)))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid connect code")
    return AuthResponse(id=user.id, email=user.email, api_token=payload.api_token)


@router.post("/telegram", response_model=AuthResponse)
def telegram_login(payload: TelegramLogin, session: Session = Depends(get_db)) -> AuthResponse:
    """Register-or-login used by the Telegram bot.

    Telegram ids are unique, so the bot can silently resume an account. The
    password is an unguessable random value; Telegram users never type it.
    The returned token doubles as the connect code shown in /start.
    """
    user = session.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    token = generate_token()
    if user is None:
        user = User(
            email=f"tg-{payload.telegram_id}@telegram.sokhan.local",
            password_hash=hash_password(generate_token()),
            token_hash=token_hash(token),
            telegram_id=payload.telegram_id,
        )
        session.add(user)
    else:
        user.token_hash = token_hash(token)
    session.commit()
    return AuthResponse(id=user.id, email=user.email, api_token=token)
