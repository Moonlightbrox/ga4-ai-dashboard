"""Centralized environment-variable access.

All configuration reads happen here so the rest of the backend never calls
``os.getenv`` directly. Keeps secrets and runtime knobs in one obvious place.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


# Load .env from the backend directory at import time so module-level reads work.
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


# OAuth scopes for the user-facing Google login. We need:
#   * analytics.readonly  -- list properties via the Admin API
#   * analytics.edit      -- create the GA4 BigQuery link via list/grant
#   * analytics.manage.users -- add the platform service account to the property
OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics.edit",
    "https://www.googleapis.com/auth/analytics.manage.users",
)

SESSION_COOKIE = "ga4_session"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def parse_allowed_origins() -> list[str]:
    """Return the CORS allowlist parsed from ``ALLOWED_ORIGINS``."""
    raw = os.getenv("ALLOWED_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_frontend_url() -> str:
    """Frontend URL the OAuth callback redirects back to."""
    return os.getenv("FRONTEND_URL", "http://localhost:3000")


def get_oauth_client_config() -> dict[str, str]:
    """Read the Google OAuth client_id/secret/redirect URI from env.

    Raises ValueError if any of the three are missing so callers can surface a
    clean 500 instead of a vague auth failure deep inside the flow.
    """
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise ValueError(
            "Missing GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / "
            "GOOGLE_OAUTH_REDIRECT_URI in environment."
        )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def get_anthropic_api_key() -> str | None:
    """Return the Anthropic API key, or None if unset."""
    return os.getenv("ANTHROPIC_API_KEY") or None


def get_anthropic_model() -> str:
    """Anthropic model id; default to the current Sonnet."""
    return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def get_frontend_dist_dir() -> str | None:
    """Optional path to a pre-built frontend bundle for static serving."""
    return os.getenv("FRONTEND_DIST") or None
