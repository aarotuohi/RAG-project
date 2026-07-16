"""
Microsoft Entra ID (Azure AD) JWT authentication for FastAPI.

Validates RS256-signed access tokens issued by the v2.0 token endpoint.
Frontend acquisition flow: Authorization Code + PKCE via MSAL (no client secret).

Security notes:
  - Token signature is verified against Microsoft's public JWKS (fetched once,
    cached 24 h, refreshed on unknown key-id for seamless key rotation).
  - Checks: RS256 alg, audience, issuer, exp, nbf.
  - AUTH_ENABLED is False when AZURE_AD_TENANT_ID / AZURE_AD_CLIENT_ID are not
    configured — allows local-only runs without Azure AD.
"""
from __future__ import annotations

import logging
import time
from typing import Annotated

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import AZURE_AD_TENANT_ID, AZURE_AD_AUDIENCE, AUTH_ENABLED

logger = logging.getLogger(__name__)

_JWKS_URL = (
    f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}/discovery/v2.0/keys"
)
_ISSUER = (
    f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}/v2.0"
)

_bearer = HTTPBearer(auto_error=True)

# ── JWKS cache ────────────────────────────────────────────────────────────────
# Tuple of ({kid: public_key}, fetched_at_monotonic).
# Keys are cached for 24 h and refreshed whenever an unknown kid is encountered
# (handles Microsoft's periodic key rotation transparently).
_jwks_cache: tuple[dict, float] | None = None
_JWKS_TTL = 86_400.0  # 24 hours


def _fetch_jwks() -> dict:
    """Fetch JWKS from Microsoft and return a {kid: RSA public key} mapping."""
    resp = httpx.get(_JWKS_URL, timeout=10)
    resp.raise_for_status()
    return {
        k["kid"]: RSAAlgorithm.from_jwk(k)
        for k in resp.json().get("keys", [])
    }


def _get_signing_key(kid: str):
    """
    Return the RSA public key for *kid*.
    Uses the cache when fresh; re-fetches on miss or expiry (key rotation).
    """
    global _jwks_cache
    now = time.monotonic()

    if _jwks_cache and now - _jwks_cache[1] < _JWKS_TTL:
        key = _jwks_cache[0].get(kid)
        if key is not None:
            return key
        # kid not in cache — might be a new key; fall through to re-fetch once

    keys = _fetch_jwks()
    _jwks_cache = (keys, now)
    return keys.get(kid)


# ── FastAPI dependency ────────────────────────────────────────────────────────

def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """
    FastAPI dependency — validates the Bearer JWT and returns its decoded claims.

    Raises HTTP 401 for missing, expired, or invalid tokens.
    When AUTH_ENABLED is False (no Azure AD vars set) the check is skipped and
    an empty claims dict is returned so local development still works.
    """
    if not AUTH_ENABLED:
        return {}

    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid", "")
        key = _get_signing_key(kid)

        if key is None:
            raise jwt.InvalidKeyError(f"No JWKS key found for kid={kid!r}")

        claims: dict = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=AZURE_AD_AUDIENCE,
            issuer=_ISSUER,
            options={"verify_exp": True, "verify_nbf": True},
        )
        return claims

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token audience mismatch — ensure AZURE_AD_AUDIENCE matches your app registration",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except httpx.HTTPError as exc:
        logger.error("JWKS fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify authentication token (JWKS fetch failed)",
        )
