"""Registration and login endpoints.

Deliberately lightweight for v1:

- email + password (scrypt-hashed) for the web dashboard; the API token is
  shown once and stored server-side only as a SHA-256 hash
- POST /auth/telegram lets the bot create or resume an account per Telegram id
- POST /auth/token-login lets a user paste the connect code shown by the bot
  to link their browser session
- POST /auth/logout revokes the caller's token
- GET /auth/session tells the dashboard who is signed in

Sign-in through the web flows (register, login, token-login) also sets the
token as an httpOnly session cookie, so the dashboard never has to keep it
in script-readable storage. The JSON body still carries `api_token` for API
clients and the bot.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from sokhan.api.deps import SESSION_COOKIE, get_current_user, get_request_token, require_bot
from sokhan.auth import (
    csrf_token_for,
    generate_token,
    hash_password,
    token_hash,
    verify_password,
)
from sokhan.config import get_settings
from sokhan.core.throttle import FailureThrottle
from sokhan.db import get_db
from sokhan.models import User
from sokhan.schemas import AuthResponse, SessionOut

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_PATTERN = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
# RFC 5321 caps a forward-path at 320 octets; 254 for the address itself.
_MAX_EMAIL_LENGTH = 254
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
    # Length check first: it bounds any regex work to a constant maximum,
    # so even a pathological input cannot burn cycles in the matcher.
    if not email or len(email) > _MAX_EMAIL_LENGTH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email address")
    if not _EMAIL_PATTERN.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email address")
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"password too short (minimum {_MIN_PASSWORD_LENGTH} characters)",
        )
    return email


def _cookie_is_secure(request: Request) -> bool:
    """Whether the session cookie gets the Secure attribute.

    `auto` (the default) follows the scheme the browser used: HTTPS directly
    or behind a proxy that sets X-Forwarded-Proto. Browsers drop a Secure
    cookie that arrives over plain http (Safari even on localhost), which
    left plain-http installs unable to stay signed in.
    """
    mode = get_settings().auth_cookie_secure.strip().lower()
    if mode in ("true", "1", "yes"):
        return True
    if mode in ("false", "0", "no"):
        return False
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def _start_session(request: Request, response: Response, user: User, token: str) -> AuthResponse:
    """Set the httpOnly session cookie and answer with the CSRF token."""
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.auth_cookie_max_age_days * 24 * 3600,
        path="/",
        httponly=True,
        secure=_cookie_is_secure(request),
        samesite=settings.auth_cookie_samesite,
    )
    return AuthResponse(
        id=user.id, email=user.email, api_token=token, csrf_token=csrf_token_for(token)
    )


def _end_session(request: Request, response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=_cookie_is_secure(request),
        samesite=settings.auth_cookie_samesite,
    )


@router.post("/register", response_model=AuthResponse)
def register(
    payload: Credentials,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> AuthResponse:
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
    return _start_session(request, response, user, token)


_login_throttle: FailureThrottle | None = None


def get_login_throttle() -> FailureThrottle:
    global _login_throttle
    if _login_throttle is None:
        settings = get_settings()
        _login_throttle = FailureThrottle(
            settings.login_max_failures, settings.login_failure_window_seconds
        )
    return _login_throttle


def reset_login_throttle() -> None:
    global _login_throttle
    _login_throttle = None


@router.post("/login", response_model=AuthResponse)
def login(
    payload: Credentials,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> AuthResponse:
    email = payload.email.strip().lower()
    throttle = get_login_throttle()
    key = (request.client.host if request.client else "", email)
    wait_seconds = throttle.retry_after(key)
    if wait_seconds:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many failed login attempts, try again later",
            headers={"Retry-After": str(wait_seconds)},
        )

    user = session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    throttle.reset(key)

    token = generate_token()
    user.token_hash = token_hash(token)
    session.commit()
    return _start_session(request, response, user, token)


@router.post("/token-login", response_model=AuthResponse)
def token_login(
    payload: TokenLogin,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> AuthResponse:
    user = session.scalar(select(User).where(User.token_hash == token_hash(payload.api_token)))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid connect code")
    return _start_session(request, response, user, payload.api_token)


@router.get("/session", response_model=SessionOut)
def current_session(
    user: User = Depends(get_current_user), token: str = Depends(get_request_token)
) -> SessionOut:
    """Who is signed in, plus the CSRF token for this session.

    The dashboard cannot read its httpOnly cookie, so it asks here after a
    reload; a 401 means signed out.
    """
    return SessionOut(id=user.id, email=user.email, csrf_token=csrf_token_for(token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    """Revoke the caller's token so it stops working everywhere.

    An account has a single active token, so this signs out every client
    that holds it: other browsers, API scripts and, for Telegram accounts,
    the bot (which re-registers on its next request). The new token is
    never returned; signing in again issues a fresh one.
    """
    user.token_hash = token_hash(generate_token())
    session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _end_session(request, response)
    return response


@router.post("/telegram", response_model=AuthResponse, dependencies=[Depends(require_bot)])
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
