"""JWT utility functions for Argenprecios auth."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from config.settings import settings


def create_access_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": email, "type": "access", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": email, "type": "refresh", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str) -> str:
    """Decode a JWT and return the email (sub claim).

    Raises JWTError if the token is invalid, expired, or the type doesn't match.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise JWTError(f"Expected token type '{expected_type}', got '{payload.get('type')}'")
    email: str = payload.get("sub", "")
    if not email:
        raise JWTError("Token missing 'sub' claim")
    return email
