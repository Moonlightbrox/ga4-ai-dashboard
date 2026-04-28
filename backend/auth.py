"""OAuth + session helpers used by every authenticated endpoint.

Owns:
    * The Google OAuth flow construction.
    * In-memory session cache (mirrored to SQLite via :mod:`backend.sessions`).
    * Cookie-based session lookup, refresh, and credential reconstruction.
    * Two convenience helpers used by routes:
        - :func:`require_user` -- session must exist + creds valid.
        - :func:`require_user_property` -- session + creds + selected property.

The route layer never imports ``backend.sessions`` or ``google.oauth2``
directly; everything goes through this module so credential refresh /
scope validation logic lives in one place.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from backend import sessions
from backend.config import (
    OAUTH_SCOPES,
    SESSION_COOKIE,
    SESSION_COOKIE_MAX_AGE,
    get_oauth_client_config,
)


# Shown when OAuth tokens are missing, revoked, expired, or lack required
# scopes. Anything that ends here forces the user to re-run the consent flow.
RECONNECT_DETAIL = (
    "Google session expired or missing required permissions. "
    "Use Reconnect / Connect GA4 to sign in again (needed after adding new OAuth scopes)."
)


# Module-level caches. Mirrored to SQLite on every mutation so a server restart
# preserves the user's session.
SESSIONS: dict[str, dict[str, Any]] = {}
STATE_INDEX: dict[str, str] = {}


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def get_oauth_flow() -> Flow:
    """Build a Google OAuth ``Flow`` configured from env."""
    try:
        cfg = get_oauth_client_config()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    client_config = {
        "web": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uris": [cfg["redirect_uri"]],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        client_config=client_config,
        scopes=list(OAUTH_SCOPES),
        redirect_uri=cfg["redirect_uri"],
    )


# ---------------------------------------------------------------------------
# Session lookup + persistence
# ---------------------------------------------------------------------------

def get_session_id(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def get_session_dict(session_id: str) -> dict[str, Any] | None:
    """Return the session payload, hydrating from SQLite on first lookup."""
    if session_id in SESSIONS:
        return SESSIONS[session_id]
    stored = sessions.load_session(session_id)
    if stored is not None:
        SESSIONS[session_id] = stored
        return stored
    return None


def persist_session(session_id: str) -> None:
    """Mirror the in-memory session to SQLite. No-op if the session is gone."""
    session = SESSIONS.get(session_id)
    if session is None:
        return
    sessions.save_session(session_id, session)


def ensure_session_id(
    request: Request,
    response: RedirectResponse | JSONResponse,
) -> str:
    """Return the active session id, creating one + cookie if absent."""
    session_id = get_session_id(request)
    if not session_id:
        session_id = str(uuid4())
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            samesite="lax",
            max_age=SESSION_COOKIE_MAX_AGE,
        )
        SESSIONS[session_id] = {}
        persist_session(session_id)
    else:
        if get_session_dict(session_id) is None:
            SESSIONS[session_id] = {}
            persist_session(session_id)
    return session_id


# ---------------------------------------------------------------------------
# Credential reconstruction
# ---------------------------------------------------------------------------

def credentials_to_dict(credentials: Credentials) -> dict[str, Any]:
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def build_user_credentials(
    session: dict[str, Any], session_id: str | None = None
) -> Credentials | None:
    """Restore credentials from the session, refreshing if needed.

    Returns ``None`` if any required scope is missing, the credentials are
    malformed, or refresh fails -- the route layer maps that to a 401 +
    :data:`RECONNECT_DETAIL`.
    """
    data = session.get("credentials")
    if not data:
        return None
    stored_scopes = set(data.get("scopes") or [])
    if not set(OAUTH_SCOPES).issubset(stored_scopes):
        session.pop("credentials", None)
        if session_id:
            persist_session(session_id)
        return None
    try:
        credentials = Credentials(**data)
    except (TypeError, ValueError):
        session.pop("credentials", None)
        if session_id:
            persist_session(session_id)
        return None
    if not credentials.valid:
        if not credentials.refresh_token:
            session.pop("credentials", None)
            if session_id:
                persist_session(session_id)
            return None
        try:
            credentials.refresh(GoogleAuthRequest())
        except RefreshError:
            session.pop("credentials", None)
            if session_id:
                persist_session(session_id)
            return None
        session["credentials"] = credentials_to_dict(credentials)
        if session_id:
            persist_session(session_id)
    return credentials


# ---------------------------------------------------------------------------
# Route guards
# ---------------------------------------------------------------------------

def require_user(request: Request) -> tuple[Credentials, str, dict[str, Any]]:
    """Return ``(credentials, session_id, session)`` or raise 401."""
    session_id = get_session_id(request)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = get_session_dict(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    credentials = build_user_credentials(session, session_id)
    if not credentials:
        raise HTTPException(status_code=401, detail=RECONNECT_DETAIL)
    return credentials, session_id, session


def require_user_property(request: Request) -> tuple[Credentials, str]:
    """Return ``(credentials, property_id)`` or raise 401/400."""
    credentials, _session_id, session = require_user(request)
    property_id = session.get("property_id")
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")
    return credentials, property_id
