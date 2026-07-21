"""
Authentication endpoints (not protected — used to obtain tokens).

  POST /api/auth/login        — validate credentials and issue a JWT
  POST /api/auth/create-user  — create a new user account (admin only)
  GET  /api/auth/me           — return the current user's profile
"""
from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from backend.auth import (
    get_user_by_username,
    verify_password,
    create_access_token,
    create_user,
    require_auth,
    require_admin,
    check_rate_limit,
    reset_rate_limit,
    init_db,
)
from backend.config import JWT_EXPIRE_SECONDS

router = APIRouter(prefix="/api/auth")

# Ensure users table exists the moment this module is imported.
init_db()


# ── Request / Response models ─────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _normalise(cls, v: str) -> str:
        return v.strip().lower()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = JWT_EXPIRE_SECONDS
    username: str
    is_admin: bool


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def _normalise(cls, v: str) -> str:
        return v.strip().lower()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Issue a JWT for valid username / password credentials."""
    # Rate-limit before touching the database to reduce timing side-channels.
    check_rate_limit(req.username)

    user = get_user_by_username(req.username)

    # Always run bcrypt to prevent timing-based user-enumeration.
    # The dummy hash is a valid bcrypt hash that will never match any real password.
    _DUMMY_HASH = "$2b$12$aaaaaaaaaaaaaaaaaaaaaOaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    stored_hash = user["password_hash"] if user else _DUMMY_HASH

    if not verify_password(req.password, stored_hash) or user is None:
        raise_invalid_credentials()

    reset_rate_limit(req.username)
    token = create_access_token(user["id"], user["username"], bool(user["is_admin"]))
    return LoginResponse(
        access_token=token,
        username=user["username"],
        is_admin=bool(user["is_admin"]),
    )


def raise_invalid_credentials():
    from fastapi import HTTPException, status
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password",
    )


@router.post("/create-user", status_code=201)
def create_new_user(
    req: CreateUserRequest,
    _admin: Annotated[dict, Depends(require_admin)],
):
    """
    Create a new user account.
    Requires the caller to present a valid admin-level JWT.
    """
    uid = create_user(req.username, req.password, req.is_admin)
    return {"id": uid, "username": req.username, "is_admin": req.is_admin}


@router.get("/me")
def get_me(claims: Annotated[dict, Depends(require_auth)]):
    """Return the profile of the currently authenticated user."""
    return {
        "user_id":  claims.get("sub"),
        "username": claims.get("username"),
        "is_admin": claims.get("is_admin", False),
    }
