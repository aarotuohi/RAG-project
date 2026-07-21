"""
Local JWT authentication for FastAPI.

Uses HS256-signed tokens issued by this server and bcrypt password hashing.
No external Identity Provider required.

Security notes:
  - Passwords are hashed with bcrypt (cost factor 12).
  - Tokens are HS256-signed with JWT_SECRET from environment.
  - Login is rate-limited per username (5 attempts per 5 minutes).
  - Constant-time bcrypt verification prevents timing-based user enumeration.
  - AUTH_ENABLED is False when JWT_SECRET is not configured — allows
    local-only runs without authentication.
"""
from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from typing import Annotated

import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import JWT_SECRET, JWT_EXPIRE_SECONDS, AUTH_ENABLED, DB_PATH

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# ── Database ──────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the users table if it does not yet exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin      INTEGER NOT NULL DEFAULT 0,
                created_at    REAL NOT NULL
            )
        """)


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── User CRUD ─────────────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> sqlite3.Row | None:
    with _get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
        ).fetchone()


def validate_password_strength(password: str) -> None:
    """Raise HTTPException 400 if the password does not meet requirements."""
    if len(password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters")
    if not any(c.isupper() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one digit")


def create_user(username: str, plain_password: str, is_admin: bool = False) -> str:
    """Hash the password and insert a new user row. Returns the new user id."""
    validate_password_strength(plain_password)
    uid = str(uuid.uuid4())
    hashed = hash_password(plain_password)
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, is_admin, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (uid, username.strip().lower(), hashed, int(is_admin), time.time()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username already exists")
    return uid


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: str, username: str, is_admin: bool) -> str:
    now = int(time.time())
    payload = {
        "sub":      user_id,
        "username": username,
        "is_admin": is_admin,
        "iat":      now,
        "exp":      now + JWT_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ── Login rate limiting (in-memory, per username) ────────────────────────────
_login_attempts: dict[str, tuple[int, float]] = {}  # username -> (count, window_start)
_MAX_ATTEMPTS   = 5
_WINDOW_SECONDS = 300  # 5 minutes


def check_rate_limit(username: str) -> None:
    now = time.time()
    count, window_start = _login_attempts.get(username, (0, now))
    if now - window_start > _WINDOW_SECONDS:
        _login_attempts[username] = (1, now)
        return
    if count >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait 5 minutes.",
        )
    _login_attempts[username] = (count + 1, window_start)


def reset_rate_limit(username: str) -> None:
    _login_attempts.pop(username, None)


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """
    FastAPI dependency — validates the Bearer JWT and returns its decoded claims.

    Raises HTTP 401 for missing, expired, or invalid tokens.
    When AUTH_ENABLED is False (JWT_SECRET not configured) the check is skipped
    and a dev-mode claims dict is returned so local development still works.
    """
    if not AUTH_ENABLED:
        return {"sub": "dev", "username": "dev", "is_admin": True}

    token = credentials.credentials
    try:
        claims: dict = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        return claims
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin(claims: Annotated[dict, Depends(require_auth)]) -> dict:
    """Extends require_auth — additionally asserts the caller is an admin."""
    if not claims.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return claims
