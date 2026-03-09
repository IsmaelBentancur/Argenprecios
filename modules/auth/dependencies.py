"""FastAPI dependencies for authentication."""

from fastapi import Cookie, Depends, HTTPException

from jose import JWTError

from config.settings import settings
from modules.auth.jwt_utils import decode_token


async def get_current_user(access_token: str | None = Cookie(default=None)) -> str:
    """Read the httpOnly 'access_token' cookie and return the authenticated email.

    Raises 401 if the token is missing or invalid.
    Raises 403 if the email is not in the allowlist.
    """
    if not access_token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    try:
        email = decode_token(access_token, expected_type="access")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    allowlist = settings.allowed_emails_set
    if allowlist and email.lower() not in allowlist:
        raise HTTPException(status_code=403, detail="Email no autorizado.")

    return email


require_auth = Depends(get_current_user)
