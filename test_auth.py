"""Tests for Google OAuth2 + JWT authentication flow.

Run with:
    python -m unittest test_auth.py
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from jose import jwt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app():
    """Build a minimal FastAPI app with auth routes mounted."""
    from fastapi import FastAPI
    from modules.auth import auth_router
    app = FastAPI()
    app.include_router(auth_router)
    return app


def _make_token(email: str, token_type: str, secret: str, algorithm: str = "HS256", expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    return jwt.encode({"sub": email, "type": token_type, "exp": expire}, secret, algorithm=algorithm)


# ---------------------------------------------------------------------------
# jwt_utils tests
# ---------------------------------------------------------------------------

class TestJWTUtils(unittest.TestCase):
    """Unit tests for jwt_utils (no I/O, no DB)."""

    def setUp(self):
        # Patch settings to have a known secret
        patcher = patch("modules.auth.jwt_utils.settings")
        self.mock_settings = patcher.start()
        self.mock_settings.jwt_secret = "testsecret"
        self.mock_settings.jwt_algorithm = "HS256"
        self.mock_settings.access_token_expire_minutes = 15
        self.mock_settings.refresh_token_expire_days = 7
        self.addCleanup(patcher.stop)

    def test_create_access_token_decodes(self):
        from modules.auth.jwt_utils import create_access_token, decode_token
        token = create_access_token("user@example.com")
        email = decode_token(token, "access")
        self.assertEqual(email, "user@example.com")

    def test_create_refresh_token_decodes(self):
        from modules.auth.jwt_utils import create_refresh_token, decode_token
        token = create_refresh_token("user@example.com")
        email = decode_token(token, "refresh")
        self.assertEqual(email, "user@example.com")

    def test_wrong_type_raises(self):
        from jose import JWTError
        from modules.auth.jwt_utils import create_access_token, decode_token
        token = create_access_token("user@example.com")
        with self.assertRaises(JWTError):
            decode_token(token, "refresh")  # wrong expected_type

    def test_expired_token_raises(self):
        from jose import JWTError
        from modules.auth.jwt_utils import decode_token
        token = _make_token("user@example.com", "access", "testsecret", expires_delta=timedelta(seconds=-1))
        with self.assertRaises(JWTError):
            decode_token(token, "access")

    def test_bad_secret_raises(self):
        from jose import JWTError
        from modules.auth.jwt_utils import decode_token
        token = _make_token("user@example.com", "access", "wrongsecret")
        with self.assertRaises(JWTError):
            decode_token(token, "access")

    def test_missing_sub_raises(self):
        from jose import JWTError
        from modules.auth.jwt_utils import decode_token
        # Token with no 'sub'
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        token = jwt.encode({"type": "access", "exp": expire}, "testsecret", algorithm="HS256")
        with self.assertRaises(JWTError):
            decode_token(token, "access")


# ---------------------------------------------------------------------------
# dependencies tests
# ---------------------------------------------------------------------------

class TestDependencies(unittest.IsolatedAsyncioTestCase):
    """Unit tests for get_current_user dependency."""

    def _patch_settings(self, allowed_emails="user@example.com"):
        patcher = patch("modules.auth.dependencies.settings")
        mock = patcher.start()
        mock.jwt_secret = "testsecret"
        mock.jwt_algorithm = "HS256"
        mock.allowed_emails_set = {e.strip().lower() for e in allowed_emails.split(",") if e.strip()}
        self.addCleanup(patcher.stop)
        return mock

    def _patch_decode(self, return_value="user@example.com", side_effect=None):
        patcher = patch("modules.auth.dependencies.decode_token")
        mock = patcher.start()
        if side_effect:
            mock.side_effect = side_effect
        else:
            mock.return_value = return_value
        self.addCleanup(patcher.stop)
        return mock

    async def test_no_cookie_raises_401(self):
        from fastapi import HTTPException
        from modules.auth.dependencies import get_current_user
        self._patch_settings()
        with self.assertRaises(HTTPException) as ctx:
            await get_current_user(access_token=None)
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        from jose import JWTError
        from modules.auth.dependencies import get_current_user
        self._patch_settings()
        self._patch_decode(side_effect=JWTError("bad"))
        with self.assertRaises(HTTPException) as ctx:
            await get_current_user(access_token="badtoken")
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_email_not_in_allowlist_raises_403(self):
        from fastapi import HTTPException
        from modules.auth.dependencies import get_current_user
        self._patch_settings(allowed_emails="other@example.com")
        self._patch_decode(return_value="user@example.com")
        with self.assertRaises(HTTPException) as ctx:
            await get_current_user(access_token="sometoken")
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_valid_token_returns_email(self):
        from modules.auth.dependencies import get_current_user
        self._patch_settings(allowed_emails="user@example.com")
        self._patch_decode(return_value="user@example.com")
        email = await get_current_user(access_token="validtoken")
        self.assertEqual(email, "user@example.com")

    async def test_empty_allowlist_allows_any_email(self):
        """When ALLOWED_EMAILS is empty, any valid token is accepted."""
        from modules.auth.dependencies import get_current_user
        self._patch_settings(allowed_emails="")
        self._patch_decode(return_value="anyone@example.com")
        email = await get_current_user(access_token="validtoken")
        self.assertEqual(email, "anyone@example.com")


# ---------------------------------------------------------------------------
# router endpoint tests (TestClient, no real Google calls)
# ---------------------------------------------------------------------------

class TestAuthRouterMe(unittest.TestCase):
    """GET /auth/me endpoint tests."""

    SECRET = "testsecret"

    def setUp(self):
        self.settings_patch = patch("modules.auth.router.settings")
        self.jwt_settings_patch = patch("modules.auth.jwt_utils.settings")
        ms = self.settings_patch.start()
        js = self.jwt_settings_patch.start()
        ms.google_client_id = "gcid"
        ms.google_client_secret = "gcsecret"
        ms.access_token_expire_minutes = 15
        ms.refresh_token_expire_days = 7
        ms.cookie_secure = False
        ms.frontend_url = "http://localhost:8000"
        ms.allowed_emails_set = {"user@example.com"}
        js.jwt_secret = self.SECRET
        js.jwt_algorithm = "HS256"
        js.access_token_expire_minutes = 15
        js.refresh_token_expire_days = 7

        from fastapi import FastAPI
        from modules.auth.router import auth_router
        app = FastAPI()
        app.include_router(auth_router)
        self.client = TestClient(app, raise_server_exceptions=True)

    def tearDown(self):
        self.settings_patch.stop()
        self.jwt_settings_patch.stop()

    def test_me_no_cookie_returns_not_authenticated(self):
        resp = self.client.get("/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["authenticated"])
        self.assertIsNone(data["email"])

    def test_me_valid_cookie_returns_email(self):
        token = _make_token("user@example.com", "access", self.SECRET)
        resp = self.client.get("/auth/me", cookies={"access_token": token})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["email"], "user@example.com")

    def test_me_expired_cookie_returns_not_authenticated(self):
        token = _make_token("user@example.com", "access", self.SECRET, expires_delta=timedelta(seconds=-1))
        resp = self.client.get("/auth/me", cookies={"access_token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["authenticated"])

    def test_me_wrong_type_returns_not_authenticated(self):
        # Pass a refresh token where an access token is expected
        token = _make_token("user@example.com", "refresh", self.SECRET)
        resp = self.client.get("/auth/me", cookies={"access_token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["authenticated"])


class TestAuthRouterRefresh(unittest.TestCase):
    """POST /auth/refresh endpoint tests."""

    def setUp(self):
        self.secret = "testsecret"
        self.settings_patch = patch("modules.auth.router.settings")
        self.jwt_settings_patch = patch("modules.auth.jwt_utils.settings")
        ms = self.settings_patch.start()
        js = self.jwt_settings_patch.start()
        for s in (ms, js):
            s.jwt_secret = self.secret
            s.jwt_algorithm = "HS256"
            s.access_token_expire_minutes = 15
            s.refresh_token_expire_days = 7
            s.cookie_secure = False
            s.frontend_url = "http://localhost:8000"
        ms.allowed_emails_set = {"user@example.com"}
        ms.google_client_id = "gcid"
        ms.google_client_secret = "gcsecret"

        from fastapi import FastAPI
        from modules.auth.router import auth_router
        app = FastAPI()
        app.include_router(auth_router)
        self.client = TestClient(app, raise_server_exceptions=True)

    def tearDown(self):
        self.settings_patch.stop()
        self.jwt_settings_patch.stop()

    def test_refresh_no_cookie_returns_401(self):
        resp = self.client.post("/auth/refresh")
        self.assertEqual(resp.status_code, 401)

    def test_refresh_invalid_token_returns_401(self):
        resp = self.client.post("/auth/refresh", cookies={"refresh_token": "garbage"})
        self.assertEqual(resp.status_code, 401)

    def test_refresh_access_token_as_refresh_returns_401(self):
        """Substituting an access token for a refresh token must fail."""
        access = _make_token("user@example.com", "access", self.secret)
        resp = self.client.post("/auth/refresh", cookies={"refresh_token": access})
        self.assertEqual(resp.status_code, 401)

    def test_refresh_valid_issues_new_access_token(self):
        refresh = _make_token("user@example.com", "refresh", self.secret)
        resp = self.client.post("/auth/refresh", cookies={"refresh_token": refresh})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access_token", resp.cookies)

    def test_refresh_not_in_allowlist_returns_403(self):
        refresh = _make_token("other@example.com", "refresh", self.secret)
        resp = self.client.post("/auth/refresh", cookies={"refresh_token": refresh})
        self.assertEqual(resp.status_code, 403)


class TestAuthRouterLogout(unittest.TestCase):
    """POST /auth/logout endpoint tests."""

    def setUp(self):
        self.settings_patch = patch("modules.auth.router.settings")
        ms = self.settings_patch.start()
        ms.cookie_secure = False
        ms.google_client_id = "gcid"
        ms.google_client_secret = "gcsecret"
        ms.jwt_secret = "testsecret"
        ms.jwt_algorithm = "HS256"
        ms.access_token_expire_minutes = 15
        ms.refresh_token_expire_days = 7
        ms.frontend_url = "http://localhost:8000"
        ms.allowed_emails_set = set()

        from fastapi import FastAPI
        from modules.auth.router import auth_router
        app = FastAPI()
        app.include_router(auth_router)
        self.client = TestClient(app, raise_server_exceptions=True)

    def tearDown(self):
        self.settings_patch.stop()

    def test_logout_clears_cookies(self):
        resp = self.client.post(
            "/auth/logout",
            cookies={"access_token": "sometoken", "refresh_token": "somerefresh"},
        )
        self.assertEqual(resp.status_code, 200)
        # After logout, the cookies should be cleared (empty value or deleted)
        # TestClient reflects Set-Cookie headers in resp.cookies with empty string when deleted
        self.assertEqual(resp.cookies.get("access_token", "DELETED"), "DELETED")
        self.assertEqual(resp.cookies.get("refresh_token", "DELETED"), "DELETED")

    def test_logout_returns_ok(self):
        resp = self.client.post("/auth/logout")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])


class TestAuthRouterLogin(unittest.TestCase):
    """GET /auth/login endpoint tests."""

    def setUp(self):
        self.settings_patch = patch("modules.auth.router.settings")
        ms = self.settings_patch.start()
        ms.google_client_id = "test-client-id"
        ms.google_client_secret = "gcsecret"
        ms.cookie_secure = False
        ms.jwt_secret = "testsecret"
        ms.jwt_algorithm = "HS256"
        ms.access_token_expire_minutes = 15
        ms.refresh_token_expire_days = 7
        ms.frontend_url = "http://localhost:8000"
        ms.allowed_emails_set = set()

        from fastapi import FastAPI
        from modules.auth.router import auth_router
        app = FastAPI()
        app.include_router(auth_router)
        self.client = TestClient(app, raise_server_exceptions=True, follow_redirects=False)

    def tearDown(self):
        self.settings_patch.stop()

    def test_login_redirects_to_google(self):
        resp = self.client.get("/auth/login")
        self.assertEqual(resp.status_code, 307)
        location = resp.headers["location"]
        self.assertIn("accounts.google.com", location)
        self.assertIn("test-client-id", location)
        self.assertIn("openid", location)

    def test_login_sets_oauth_state_cookie(self):
        resp = self.client.get("/auth/login")
        self.assertIn("oauth_state", resp.cookies)


class TestAuthRouterCallback(unittest.TestCase):
    """GET /auth/callback endpoint tests (mocks Google HTTP calls)."""

    SECRET = "testsecret"

    def setUp(self):
        self._active_patches: list = []

    def tearDown(self):
        for p in self._active_patches:
            p.stop()
        self._active_patches.clear()

    def _build_client(self, allowed_emails="user@example.com"):
        sp = patch("modules.auth.router.settings")
        jp = patch("modules.auth.jwt_utils.settings")
        ms = sp.start()
        js = jp.start()
        self._active_patches.extend([sp, jp])

        ms.google_client_id = "gcid"
        ms.google_client_secret = "gcsecret"
        ms.cookie_secure = False
        ms.jwt_secret = self.SECRET
        ms.jwt_algorithm = "HS256"
        ms.access_token_expire_minutes = 15
        ms.refresh_token_expire_days = 7
        ms.frontend_url = "http://localhost:8000"
        ms.allowed_emails_set = {e.strip().lower() for e in allowed_emails.split(",") if e.strip()}
        js.jwt_secret = self.SECRET
        js.jwt_algorithm = "HS256"
        js.access_token_expire_minutes = 15
        js.refresh_token_expire_days = 7

        from fastapi import FastAPI
        from modules.auth.router import auth_router
        app = FastAPI()
        app.include_router(auth_router)
        return TestClient(app, raise_server_exceptions=True, follow_redirects=False)

    def _mock_google(self, email="user@example.com", token_status=200, info_status=200):
        token_resp = MagicMock()
        token_resp.status_code = token_status
        token_resp.json.return_value = {"access_token": "google-at"}

        info_resp = MagicMock()
        info_resp.status_code = info_status
        info_resp.json.return_value = {"email": email}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=token_resp)
        mock_client.get = AsyncMock(return_value=info_resp)
        return mock_client

    def test_callback_invalid_state_returns_400(self):
        client = self._build_client()
        resp = client.get("/auth/callback?code=abc&state=wrong", cookies={"oauth_state": "correct"})
        self.assertEqual(resp.status_code, 400)

    def test_callback_missing_state_cookie_returns_400(self):
        client = self._build_client()
        resp = client.get("/auth/callback?code=abc&state=somestate")
        self.assertEqual(resp.status_code, 400)

    def test_callback_google_token_error_returns_502(self):
        client = self._build_client()
        mock_client = self._mock_google(token_status=400)
        with patch("modules.auth.router.httpx.AsyncClient", return_value=mock_client):
            resp = client.get(
                "/auth/callback?code=abc&state=mystate",
                cookies={"oauth_state": "mystate"},
            )
        self.assertEqual(resp.status_code, 502)

    def test_callback_email_not_in_allowlist_returns_403(self):
        client = self._build_client(allowed_emails="other@example.com")
        mock_client = self._mock_google(email="user@example.com")
        with patch("modules.auth.router.httpx.AsyncClient", return_value=mock_client):
            resp = client.get(
                "/auth/callback?code=abc&state=mystate",
                cookies={"oauth_state": "mystate"},
            )
        self.assertEqual(resp.status_code, 403)

    def test_callback_success_sets_cookies_and_redirects(self):
        client = self._build_client(allowed_emails="user@example.com")
        mock_client = self._mock_google(email="user@example.com")
        with patch("modules.auth.router.httpx.AsyncClient", return_value=mock_client):
            resp = client.get(
                "/auth/callback?code=abc&state=mystate",
                cookies={"oauth_state": "mystate"},
            )
        self.assertIn(resp.status_code, (302, 307))
        self.assertIn("access_token", resp.cookies)
        self.assertIn("refresh_token", resp.cookies)
        self.assertEqual(resp.headers["location"], "http://localhost:8000")


if __name__ == "__main__":
    unittest.main()
