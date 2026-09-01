"""Password hashing and JWT issuing.

We use the ``bcrypt`` package DIRECTLY rather than ``passlib.CryptContext``.

Why: passlib 1.7.4 reads ``bcrypt.__about__.__version__``, which was removed in
bcrypt 4.1. Against the installed bcrypt 4.3.0 it still produces a correct hash
but emits a trapped AttributeError traceback on *every* hash operation -- noisy
in logs and a fragile coupling to keep in a demo. Verified on this machine; see
PROJECT_STATE.md -> Environment Audit.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt. Returns a UTF-8 string for DB storage."""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time password check. Never raises on malformed stored hashes."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Corrupt or non-bcrypt hash in the DB -- deny rather than 500.
        return False


def create_access_token(
    *,
    user_id: int,
    role: str,
    client_id: int | None,
    expires_minutes: int | None = None,
) -> str:
    """Issue a signed JWT.

    ``client_id`` is embedded in the token and is the ONLY source of tenant
    scoping at request time. It is never read from a query string or body.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "client_id": client_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT. Returns None for any invalid/expired token.

    Returning None rather than raising keeps the caller's 401 handling in one
    place and avoids leaking the reason a token failed.
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
