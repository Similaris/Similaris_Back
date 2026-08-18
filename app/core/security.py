from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_token(
    subject: str, token_type: str, expire_minutes: int
) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": subject, "type": token_type, "exp": expires_at}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm), expires_at


def create_access_token(subject: str) -> str:
    token, _ = _create_token(subject, "access", settings.access_token_expire_minutes)
    return token


def create_refresh_token(subject: str) -> str:
    token, _ = _create_token(
        subject, "refresh", settings.refresh_token_expire_minutes
    )
    return token


def _decode_token(token: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload if payload.get("type") == expected_type else None
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> str | None:
    """Returns the subject from a valid access token only."""
    payload = _decode_token(token, "access")
    return payload.get("sub") if payload else None


def decode_refresh_token(token: str) -> str | None:
    """Returns the subject from a valid refresh token only."""
    payload = _decode_token(token, "refresh")
    return payload.get("sub") if payload else None
