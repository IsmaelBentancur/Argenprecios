"""OAuth2 + JWT authentication router for Argenprecios."""

import secrets

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from jose import JWTError

from config.settings import settings
from modules.auth.jwt_utils import create_access_token, create_refresh_token, decode_token

auth_router = APIRouter(prefix="/auth", tags=["auth"])

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_COOKIE_KWARGS = dict(
    httponly=True,
    secure=settings.cookie_secure,
    samesite="lax",
    path="/",
)


@auth_router.get("/login")
async def login(request: Request):
    """Redirect the browser to Google's OAuth2 consent screen."""
    state = secrets.token_urlsafe(32)
    redirect_uri = str(request.base_url).rstrip("/") + "/auth/callback"
    google_url = (
        f"{_GOOGLE_AUTH_URL}"
        f"?client_id={settings.google_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={state}"
    )
    response = RedirectResponse(url=google_url)
    response.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        **_COOKIE_KWARGS,
    )
    return response


@auth_router.get("/callback")
async def callback(
    request: Request,
    code: str = "",
    state: str = "",
    oauth_state: str | None = Cookie(default=None),
):
    """Handle Google OAuth2 callback, issue our JWT cookies, redirect to app."""
    # CSRF: verify state matches the cookie we set
    if not state or state != oauth_state:
        raise HTTPException(status_code=400, detail="Estado OAuth inválido (posible CSRF).")

    redirect_uri = str(request.base_url).rstrip("/") + "/auth/callback"

    # Exchange code for Google tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Error al intercambiar código con Google.")

    google_access_token = token_resp.json().get("access_token")

    # Fetch user email from Google
    async with httpx.AsyncClient() as client:
        info_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
    if info_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Error al obtener perfil de Google.")

    email: str = info_resp.json().get("email", "").lower()
    if not email:
        raise HTTPException(status_code=502, detail="Google no devolvió un email.")

    # Check allowlist
    allowlist = settings.allowed_emails_set
    if allowlist and email not in allowlist:
        raise HTTPException(status_code=403, detail="Email no autorizado.")

    # Issue our tokens
    access_token = create_access_token(email)
    refresh_token = create_refresh_token(email)

    response = RedirectResponse(url=settings.frontend_url)
    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        **_COOKIE_KWARGS,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        **_COOKIE_KWARGS,
    )
    # Remove the state cookie
    response.delete_cookie("oauth_state", path="/")
    return response


@auth_router.post("/refresh")
async def refresh(refresh_token: str | None = Cookie(default=None)):
    """Use refresh_token cookie to issue a new access_token cookie."""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No hay refresh token.")
    try:
        email = decode_token(refresh_token, expected_type="refresh")
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado.")

    allowlist = settings.allowed_emails_set
    if allowlist and email.lower() not in allowlist:
        raise HTTPException(status_code=403, detail="Email no autorizado.")

    new_access = create_access_token(email)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "access_token",
        new_access,
        max_age=settings.access_token_expire_minutes * 60,
        **_COOKIE_KWARGS,
    )
    return response


@auth_router.post("/logout")
async def logout():
    """Clear auth cookies (stateless logout)."""
    response = JSONResponse({"ok": True})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return response


@auth_router.get("/me")
async def me(access_token: str | None = Cookie(default=None)):
    """Return the authenticated user's email, or {authenticated: false}."""
    if not access_token:
        return {"authenticated": False, "email": None}
    try:
        email = decode_token(access_token, expected_type="access")
    except JWTError:
        return {"authenticated": False, "email": None}

    allowlist = settings.allowed_emails_set
    if allowlist and email.lower() not in allowlist:
        return {"authenticated": False, "email": None}

    return {"authenticated": True, "email": email}
