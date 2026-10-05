"""Local caregiver sessions; optional Cognito access-token verification.

Household identity comes only from a verified session/token, never a model argument.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextvars import ContextVar

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

household: ContextVar[int | None] = ContextVar("household", default=None)
COOKIE = "dose_session"
TTL = 12 * 60 * 60
SCHEMA = """
CREATE TABLE IF NOT EXISTS households (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);
INSERT OR IGNORE INTO households (id, name) VALUES (1, 'Demo');
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
 household_id INTEGER NOT NULL, cognito_sub TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, account_id INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (email TEXT PRIMARY KEY, count INTEGER NOT NULL, since INTEGER NOT NULL);
"""


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return salt + ":" + derived.hex()


class Auth:
    def __init__(self, store):
        self.store = store
        self.provider = os.environ.get("DOSE_AUTH_PROVIDER", "local")
        if self.provider not in {"local", "demo", "cognito"}:
            raise ValueError("DOSE_AUTH_PROVIDER must be local, demo, or cognito")
        with store.connect() as conn:
            conn.executescript(SCHEMA)
        self.jwks = None
        if self.provider == "cognito":
            if os.environ.get("AWS_ENABLED", "0") != "1":
                raise ValueError("Cognito requires AWS_ENABLED=1; use local while offline")
            import jwt
            region = os.environ["AWS_REGION"]
            pool = os.environ["COGNITO_USER_POOL_ID"]
            if not region.replace("-", "").isalnum() or not pool.replace("_", "").replace("-", "").isalnum():
                raise ValueError("Invalid Cognito region or pool ID")
            self.issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool}"
            self.client_id = os.environ["COGNITO_CLIENT_ID"]
            self.jwks = jwt.PyJWKClient(self.issuer + "/.well-known/jwks.json", timeout=5)

    def identity(self, request: Request):
        if self.provider == "demo":
            return {"household_id": 1, "email": "Demo", "household_name": "Demo"}
        if self.provider == "cognito":
            import jwt
            header = request.headers.get("authorization", "")
            if not header.startswith("Bearer "):
                return None
            token = header[7:]
            try:
                key = self.jwks.get_signing_key_from_jwt(token).key
                claims = jwt.decode(token, key, algorithms=["RS256"], issuer=self.issuer,
                                    options={"verify_aud": False, "require": ["sub", "exp", "iat", "iss", "token_use", "client_id"]})
                if claims["token_use"] != "access" or claims["client_id"] != self.client_id:
                    return None
                # No automatic household assignment from user-controlled claims.
                with self.store.connect() as conn:
                    row = conn.execute("SELECT a.email, a.household_id, h.name AS household_name FROM accounts a JOIN households h ON h.id=a.household_id WHERE a.cognito_sub=?", (claims["sub"],)).fetchone()
                return dict(row) if row else None
            except (jwt.PyJWTError, ValueError):
                return None
        token = request.cookies.get(COOKIE, "")
        if not token:
            return None
        with self.store.connect() as conn:
            row = conn.execute("SELECT a.email, a.household_id, h.name AS household_name FROM sessions s JOIN accounts a ON a.id=s.account_id JOIN households h ON h.id=a.household_id WHERE s.token_hash=? AND s.expires>?", (digest(token), int(time.time()))).fetchone()
        return dict(row) if row else None

    def credentials(self, body):
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        if len(email) > 254 or "@" not in email or len(password) < 12 or len(password) > 256:
            raise ValueError("Enter an email and a password between 12 and 256 characters.")
        return email, password

    def create(self, body):
        email, password = self.credentials(body)
        name = " ".join(str(body.get("household_name", "")).split())
        if not 1 <= len(name) <= 80:
            raise ValueError("Enter a household name (up to 80 characters).")
        hashed = password_hash(password)
        with self.store.connect() as conn:
            # A single transaction prevents an orphan household on duplicate email.
            hid = conn.execute("INSERT INTO households (name) VALUES (?)", (name,)).lastrowid
            account = conn.execute("INSERT INTO accounts (email,password,household_id) VALUES (?,?,?)", (email, hashed, hid)).lastrowid
        return account

    def login(self, body):
        email, password = self.credentials(body)
        now = int(time.time())
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            attempt = conn.execute("SELECT count,since FROM login_attempts WHERE email=?", (email,)).fetchone()
            if attempt and now - attempt["since"] < 900 and attempt["count"] >= 10:
                raise ValueError("Too many attempts. Try again in 15 minutes.")
            count = attempt["count"] + 1 if attempt and now - attempt["since"] < 900 else 1
            since = attempt["since"] if count > 1 else now
            conn.execute("INSERT OR REPLACE INTO login_attempts VALUES (?,?,?)", (email, count, since))
            row = conn.execute("SELECT id,password FROM accounts WHERE email=? AND cognito_sub IS NULL", (email,)).fetchone()
        stored = row["password"] if row else "0" * 32 + ":" + "0" * 64
        actual = password_hash(password, stored.split(":")[0])
        if not hmac.compare_digest(stored, actual):
            raise ValueError("Email or password is incorrect.")
        with self.store.connect() as conn:
            conn.execute("DELETE FROM login_attempts WHERE email=?", (email,))
        return row["id"]

    def session(self, account):
        token = secrets.token_urlsafe(32)
        with self.store.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))
            conn.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), account, int(time.time()) + TTL))
        return token

    async def endpoint(self, request):
        action = request.path_params["action"]
        if action == "session" and request.method == "GET":
            identity = await run_in_threadpool(self.identity, request)
            return JSONResponse({"authenticated": bool(identity), "provider": self.provider, "identity": identity})
        if self.provider != "local":
            return JSONResponse({"error": "Password login is available in local mode only."}, status_code=400)
        if request.method != "POST" or action not in {"register", "login", "logout"}:
            return JSONResponse({"error": "Unknown action."}, status_code=404)
        if action == "logout":
            with self.store.connect() as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (digest(request.cookies.get(COOKIE, "")),))
            response = JSONResponse({"ok": True})
            response.delete_cookie(COOKIE)
            return response
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"error": "Use application/json."}, status_code=415)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Expected an object.")
            account = await run_in_threadpool(self.create if action == "register" else self.login, body)
            token = await run_in_threadpool(self.session, account)
        except (ValueError, sqlite3.IntegrityError):
            return JSONResponse({"error": "Registration or login failed. Check your details, or try again later."}, status_code=400)
        response = JSONResponse({"ok": True})
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=TTL)
        response.headers["Cache-Control"] = "no-store"
        return response


class HouseholdMiddleware:
    def __init__(self, app, auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        # Reject browser cross-origin writes, including password login and MCP.
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return await JSONResponse({"error": "Cross-origin writes are disabled."}, status_code=403)(scope, receive, send)
        path = request.url.path
        public = path in {"/login", "/api/health"} or path.startswith(("/static/", "/api/auth/"))
        identity = None if public else await run_in_threadpool(self.auth.identity, request)
        if not public and not identity:
            response = RedirectResponse("/login", status_code=303) if path in {"/", "/agent"} else JSONResponse({"error": "Sign in first."}, status_code=401)
            return await response(scope, receive, send)
        token = household.set(identity["household_id"] if identity else None)
        async def no_cache(message):
            if message["type"] == "http.response.start" and not path.startswith("/static/"):
                message["headers"] = [(k, v) for k, v in message["headers"] if k.lower() != b"cache-control"] + [(b"cache-control", b"no-store")]
            await send(message)
        try:
            await self.app(scope, receive, no_cache)
        finally:
            household.reset(token)
