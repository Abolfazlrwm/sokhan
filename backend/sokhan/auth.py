"""Password hashing and API token helpers.

Deliberately standard-library only: scrypt for passwords, SHA-256 for token
verification (the raw token is never stored server-side).
"""

import hashlib
import hmac
import secrets

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt.encode("ascii"), n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    ).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(
        password.encode("utf-8"), salt=salt.encode("ascii"), n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    ).hex()
    return hmac.compare_digest(candidate, digest)


def generate_token() -> str:
    return secrets.token_hex(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
