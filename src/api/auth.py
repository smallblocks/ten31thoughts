"""
Ten31 Thoughts - Authentication
Single-user PIN-based auth with 90-day session cookies.
PIN hash is stored in /data/store.json by StartOS action.
Auth is dormant until a PIN is set.
"""

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE = "thoughts_session"
SESSION_MAX_AGE = 90 * 24 * 60 * 60  # 90 days in seconds
STORE_PATH = "/data/store.json"

# In-memory session store (survives within process lifetime; cleared on restart)
# For a single-user app this is fine — one active session at a time.
_sessions: dict[str, dict] = {}


def _read_pin_hash() -> Optional[str]:
    """Read the PIN hash from the StartOS store file.
    Returns None if not set or empty (auth disabled)."""
    try:
        with open(STORE_PATH, "r") as f:
            store = json.load(f)
        pin_hash = store.get("pinHash", "")
        return pin_hash if pin_hash else None
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def auth_enabled() -> bool:
    """Auth is enabled if a PIN hash exists in store.json."""
    return _read_pin_hash() is not None


def _hash_pin(pin: str) -> str:
    """Hash a PIN with SHA-256."""
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def _verify_pin(pin: str, pin_hash: str) -> bool:
    return _hash_pin(pin) == pin_hash


def create_session() -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE)
    _sessions[token] = {"expires_at": expires}
    return token


def validate_session(token: Optional[str]) -> bool:
    """Check if a session token is valid."""
    if not token:
        return False
    session = _sessions.get(token)
    if not session:
        return False
    if session["expires_at"] < datetime.now(timezone.utc):
        _sessions.pop(token, None)
        return False
    return True


def invalidate_all_sessions():
    """Clear all sessions (called when PIN changes)."""
    _sessions.clear()


# ─── Public endpoints (no auth needed) ──────────────────────────────────────

PUBLIC_PATHS = {
    "/api/auth/status",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/health",
}


class LoginRequest(BaseModel):
    pin: str


@router.get("/status")
def auth_status(request: Request):
    """Check if auth is enabled and if the current session is valid."""
    enabled = auth_enabled()
    token = request.cookies.get(SESSION_COOKIE)
    authenticated = validate_session(token) if token else False
    return {
        "authEnabled": enabled,
        "authenticated": authenticated,
    }


@router.post("/login")
def login(req: LoginRequest, response: Response):
    """Authenticate with PIN, set session cookie."""
    pin = req.pin.strip()
    pin_hash = _read_pin_hash()

    if not pin_hash:
        raise HTTPException(status_code=403, detail="No PIN configured. Set one via StartOS Actions.")

    if not _verify_pin(pin, pin_hash):
        raise HTTPException(status_code=401, detail="Invalid PIN")

    token = create_session()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"status": "ok"}


@router.post("/logout")
def logout(request: Request, response: Response):
    """Clear session cookie and invalidate token."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _sessions.pop(token, None)
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"status": "logged out"}
