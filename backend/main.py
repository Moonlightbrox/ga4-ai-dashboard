"""
This module defines the FastAPI backend for the GA4 AI dashboard. It wires
OAuth login, GA4 report fetching, AI analysis, and optional static frontend
serving into a single API service.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from dotenv import load_dotenv
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel, Field

from backend.ai.cloud import analyze_selected_reports
from backend.analytics.raw_reports import get_all_core_reports
from backend.data.ga4_schema import CORE_REPORT_DIMENSIONS, CORE_REPORT_METRICS
from backend.data.ga4_service import fetch_ga4_report, ga4_request_context
from backend.data.preprocess import ga4_to_dataframe


# ------------------------------------------------------------------------------
# Environment setup and application configuration
# ------------------------------------------------------------------------------

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))  # Local env file path for secrets.
load_dotenv(dotenv_path=ENV_PATH)                                            # Load environment variables at startup.

app = FastAPI()                                                              # FastAPI app instance for the backend.

OAUTH_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]        # GA4 read-only scope for OAuth.
SESSION_COOKIE = "ga4_session"                                               # Cookie name for session tracking.
SESSIONS: dict[str, dict[str, Any]] = {}                                     # In-memory session store keyed by session_id.
STATE_INDEX: dict[str, str] = {}                                             # Map OAuth state -> session_id for callbacks.


# ------------------------------------------------------------------------------
# Utility helpers for configuration and data conversion
# ------------------------------------------------------------------------------

# This function parses the CORS allowlist from the environment.
def _parse_allowed_origins() -> list[str]:                                   # Parse comma-separated CORS origins.
    raw = os.getenv("ALLOWED_ORIGINS", "")                                   # Raw env string of allowed origins.
    return [origin.strip() for origin in raw.split(",") if origin.strip()]   # Return cleaned origin list.


# CORS middleware to allow frontend requests with cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins() or ["http://localhost:3000"],     # Use env allowlist or local default.
    allow_credentials=True,                                                  # Allow cookies for session auth.
    allow_methods=["*"],                                                     # Allow all HTTP methods.
    allow_headers=["*"],                                                     # Allow all headers.
)


# This function converts a DataFrame to JSON-ready records.
def _df_to_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:          # Normalize DataFrame to list of dicts.
    if df is None:
        return []                                                            # Return empty list when no data.
    if getattr(df, "empty", False):
        return []                                                            # Return empty list when DataFrame is empty.
    return df.to_dict(orient="records")                                      # Return rows as JSON-friendly records.


# This function converts JSON records back into a DataFrame.
def _records_to_df(rows: list[dict[str, Any]] | None) -> pd.DataFrame:        # Normalize records into a DataFrame.
    if not rows:
        return pd.DataFrame()                                                # Return empty DataFrame when no rows.
    return pd.DataFrame(rows)                                                # Return DataFrame for downstream logic.


# This function returns the frontend URL used after OAuth.
def _get_frontend_url() -> str:                                              # Resolve frontend redirect URL.
    return os.getenv("FRONTEND_URL", "http://localhost:3000")                # Return env URL or local default.


# This function builds the Google OAuth flow configuration.
def _get_oauth_flow() -> Flow:                                               # Create OAuth flow with env config.
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")                          # OAuth client ID.
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")                  # OAuth client secret.
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")                    # OAuth redirect URL.
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="Missing GOOGLE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI",
        )
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        client_config=client_config,
        scopes=OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )                                                                         # Return configured OAuth Flow object.


# This function reads the session id from request cookies.
def _get_session_id(request: Request) -> str | None:                         # Read session cookie from the request.
    return request.cookies.get(SESSION_COOKIE)                               # Return cookie value or None.


# This function ensures a session exists and sets a cookie if needed.
def _ensure_session_id(
    request: Request,                                                        # Incoming request for cookie lookup.
    response: RedirectResponse | JSONResponse,                               # Response to set cookie on.
) -> str:
    session_id = _get_session_id(request)                                    # Existing session id from cookies.
    if not session_id:
        session_id = str(uuid4())                                            # Generate a new session id.
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            samesite="lax",
        )
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {}                                            # Initialize a new session dict.
    return session_id                                                         # Return the active session id.


# This function serializes Google credentials for session storage.
def _credentials_to_dict(credentials: Credentials) -> dict[str, Any]:        # Flatten credential fields for storage.
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }                                                                         # Return a serializable credential dict.


# This function reconstructs credentials and refreshes them if expired.
def _build_user_credentials(session: dict[str, Any]) -> Credentials | None:  # Restore credentials from session.
    data = session.get("credentials")                                        # Stored credential dict.
    if not data:
        return None                                                          # Return None when no credentials saved.
    credentials = Credentials(**data)                                        # Rebuild Credentials from dict.
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleAuthRequest())                             # Refresh tokens on demand.
        session["credentials"] = _credentials_to_dict(credentials)           # Persist refreshed credentials.
    return credentials                                                        # Return valid Credentials object.


# This function enforces that a user is authenticated and has a property selected.
def _require_user_context(request: Request) -> tuple[Credentials, str]:      # Validate session and property.
    session_id = _get_session_id(request)                                    # Read current session id.
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = SESSIONS[session_id]                                           # Session data for this user.
    credentials = _build_user_credentials(session)                           # Credentials for GA4 API calls.
    if not credentials:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    property_id = session.get("property_id")                                 # Selected GA4 property id.
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")
    return credentials, property_id                                           # Return validated context tuple.


# ------------------------------------------------------------------------------
# Request/response schemas for API payloads
# ------------------------------------------------------------------------------

# This model captures parameters for ad-hoc custom GA4 reports.
class CustomReportRequest(BaseModel):
    start_date: str                                                          # Report start date (YYYY-MM-DD).
    end_date: str                                                            # Report end date (YYYY-MM-DD).
    metrics: List[str] = Field(default_factory=list)                         # GA4 metric names to request.
    dimensions: List[str] = Field(default_factory=list)                      # GA4 dimension names to request.


# This model represents a report payload passed between frontend and backend.
class ReportPayload(BaseModel):
    id: str                                                                  # Stable report identifier.
    name: str                                                                # Human-readable report name.
    description: str                                                         # Report summary for display.
    data: List[Dict[str, Any]] = Field(default_factory=list)                 # Report rows as JSON records.


# This model captures the request body for AI analysis.
class AnalyzeRequest(BaseModel):
    selected_reports: List[ReportPayload] = Field(default_factory=list)      # Reports selected for analysis.
    user_question: str                                                       # Natural-language user question.
    prompt_key: Optional[str] = None                                         # Optional template key for prompts.


# ------------------------------------------------------------------------------
# Core API endpoints
# ------------------------------------------------------------------------------

# This endpoint reports service health for monitoring.
@app.get("/api/health")
def health() -> dict[str, str]:                                              # Health check endpoint.
    return {"status": "ok"}                                                  # Return status marker for uptime checks.


# This endpoint starts the OAuth login flow with Google.
@app.get("/api/auth/login")
def auth_login(request: Request):                                            # Begin OAuth login and redirect.
    state = str(uuid4())                                                     # Random state token for CSRF protection.
    flow = _get_oauth_flow()                                                 # Build OAuth flow configuration.
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    response = RedirectResponse(authorization_url)                           # Redirect user to Google consent.
    session_id = _ensure_session_id(request, response)                       # Ensure a session and cookie.
    SESSIONS[session_id]["oauth_state"] = state                              # Save state to session.
    STATE_INDEX[state] = session_id                                          # Map state to session for callback.
    return response                                                          # Return the redirect response.


# This endpoint completes OAuth and stores credentials in the session.
@app.get("/api/auth/callback")
def auth_callback(request: Request):                                         # Handle OAuth callback from Google.
    state = request.query_params.get("state")                                # OAuth state from query params.
    session_id = _get_session_id(request) or (STATE_INDEX.get(state) if state else None)
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=400, detail="Invalid session.")
    session = SESSIONS[session_id]                                           # Session for this callback.
    if state != session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    flow = _get_oauth_flow()                                                 # Rebuild OAuth flow for token exchange.
    flow.fetch_token(authorization_response=str(request.url))                # Exchange auth code for tokens.
    session["credentials"] = _credentials_to_dict(flow.credentials)          # Persist credentials in session.
    session.pop("property_id", None)                                         # Clear any prior property selection.
    response = RedirectResponse(f"{_get_frontend_url()}?connected=1")         # Redirect back to frontend.
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
    )
    return response                                                          # Return redirect with session cookie.


# This endpoint reports whether the session is authenticated.
@app.get("/api/auth/status")
def auth_status(request: Request):                                           # Check current auth status.
    session_id = _get_session_id(request)                                    # Read session id from cookie.
    if not session_id or session_id not in SESSIONS:
        return {"connected": False}                                          # Return false when no session.
    session = SESSIONS[session_id]                                           # Session data for this user.
    return {"connected": bool(session.get("credentials"))}                   # Return true when credentials exist.


# This endpoint lists GA4 properties accessible to the user.
@app.get("/api/ga4/properties")
def list_properties(request: Request):                                       # Fetch available GA4 properties.
    session_id = _get_session_id(request)                                    # Read session id from cookie.
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = SESSIONS[session_id]                                           # Session data for this user.
    credentials = _build_user_credentials(session)                           # Build credentials for API calls.
    if not credentials:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")

    client = AnalyticsAdminServiceClient(credentials=credentials)            # Admin API client for properties.
    summaries = client.list_account_summaries()                              # Fetch account summaries.
    properties = []                                                          # Accumulate property metadata for UI.
    for summary in summaries:
        for prop in summary.property_summaries:
            property_name = prop.property or ""                              # Resource name (properties/ID).
            property_id = property_name.split("/")[-1] if property_name else ""
            properties.append(
                {
                    "property_id": property_id,
                    "display_name": prop.display_name,
                }
            )

    return {"properties": properties}                                        # Return property list for UI.


# This model captures the chosen GA4 property id.
class PropertySelection(BaseModel):
    property_id: str                                                         # Selected GA4 property id.


# This endpoint saves the selected GA4 property for the session.
@app.post("/api/ga4/select-property")
def select_property(
    request: Request,                                                        # Incoming request with session cookie.
    payload: PropertySelection,                                              # Selected property payload.
):
    session_id = _get_session_id(request)                                    # Read session id from cookie.
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = SESSIONS[session_id]                                           # Session data for this user.
    session["property_id"] = payload.property_id                             # Store selection for later queries.
    return {"selected": payload.property_id}                                 # Return selection confirmation.


# ------------------------------------------------------------------------------
# Report generation endpoints
# ------------------------------------------------------------------------------

# This endpoint exposes the allowed metrics and dimensions for custom reports.
@app.get("/api/reports/schema")
def get_report_schema() -> dict[str, Any]:                                   # Provide UI metadata for report builders.
    metrics = [                                                              # Build metric payloads with labels.
        {
            "id": metric_id,
            "label": meta.get("label", metric_id),
            "description": meta.get("description", ""),
        }
        for metric_id, meta in CORE_REPORT_METRICS.items()
    ]
    dimensions = [                                                           # Build dimension payloads with labels.
        {
            "id": dimension_id,
            "label": meta.get("label", dimension_id),
            "description": meta.get("description", ""),
        }
        for dimension_id, meta in CORE_REPORT_DIMENSIONS.items()
    ]
    return {"metrics": metrics, "dimensions": dimensions}                    # Return schema payload for the frontend.

# This endpoint fetches the bundled set of core reports.
@app.get("/api/reports/core")
def get_core_reports(
    start: str,                                                              # Start date for the report window.
    end: str,                                                                # End date for the report window.
    request: Request,                                                        # Incoming request with session cookie.
) -> dict[str, Any]:
    credentials, property_id = _require_user_context(request)                # Validate auth and property.
    try:
        with ga4_request_context(property_id=property_id, credentials=credentials):
            reports = get_all_core_reports(start, end)                       # Execute all report builders.
    except Exception as exc:                                                 # Handle GA4 or report errors cleanly.
        raise HTTPException(status_code=500, detail=str(exc))

    payload = []                                                             # Accumulate serialized report payloads.
    for report in reports.values():
        payload.append(
            {
                "id": report["id"],
                "name": report["name"],
                "description": report["description"],
                "data": _df_to_records(report.get("data")),
            }
        )

    return {"reports": payload}                                              # Return reports for frontend rendering.


# This endpoint fetches a custom GA4 report with user-selected fields.
@app.post("/api/reports/custom")
def create_custom_report(
    req: CustomReportRequest,                                                # Custom report request payload.
    request: Request,                                                        # Incoming request with session cookie.
) -> dict[str, Any]:
    credentials, property_id = _require_user_context(request)                # Validate auth and property.
    try:
        with ga4_request_context(property_id=property_id, credentials=credentials):
            response = fetch_ga4_report(
                start_date=req.start_date,
                end_date=req.end_date,
                metrics=req.metrics,
                dimensions=req.dimensions,
            )
    except Exception as exc:                                                 # Handle GA4 API failures.
        raise HTTPException(status_code=500, detail=str(exc))

    df = ga4_to_dataframe(response)                                          # Normalize GA4 response into DataFrame.
    return {"data": _df_to_records(df)}                                      # Return serialized report rows.


# ------------------------------------------------------------------------------
# AI analysis endpoint
# ------------------------------------------------------------------------------

# This endpoint runs AI analysis on selected reports and a user question.
@app.post("/api/ai/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:                          # Run AI analysis on report data.
    reports = []                                                             # Build internal report list with DataFrames.
    for report in req.selected_reports:
        reports.append(
            {
                "id": report.id,
                "name": report.name,
                "description": report.description,
                "data": _records_to_df(report.data),
            }
        )

    try:
        answer = analyze_selected_reports(
            selected_reports=reports,
            user_question=req.user_question,
            prompt_key=req.prompt_key,
        )
    except Exception as exc:                                                 # Handle AI/prompt errors safely.
        raise HTTPException(status_code=500, detail=str(exc))

    return {"answer": answer}                                                # Return AI response text to client.


# ------------------------------------------------------------------------------
# Static frontend serving (optional)
# ------------------------------------------------------------------------------

_FRONTEND_DIST = os.getenv("FRONTEND_DIST")                                  # Path to built frontend assets.


# This function resolves safe static file paths under the frontend dist.
def _resolve_static_path(path: str) -> str | None:                           # Safely map URL path to file path.
    if not _FRONTEND_DIST:
        return None                                                          # Return None when no dist is configured.
    normalized = os.path.normpath(path.lstrip("/"))                          # Normalize to avoid path traversal.
    candidate = os.path.abspath(os.path.join(_FRONTEND_DIST, normalized))    # Candidate file path in dist.
    base = os.path.abspath(_FRONTEND_DIST)                                   # Base directory to enforce bounds.
    if os.path.commonpath([candidate, base]) != base:
        return None                                                          # Reject paths outside of dist root.
    if os.path.isfile(candidate):
        return candidate                                                     # Return the static file path.
    return None                                                              # Return None when file does not exist.


# This endpoint serves the frontend index if assets are available.
@app.get("/")
def serve_index():                                                           # Serve the SPA index page.
    index_path = _resolve_static_path("index.html")                          # Resolve index.html in dist.
    if not index_path:
        raise HTTPException(status_code=404)
    return FileResponse(index_path)                                          # Return index.html as a file response.


# This endpoint serves static assets or falls back to index for SPA routing.
@app.get("/{path:path}")
def serve_static(path: str):                                                 # Serve static asset or SPA fallback.
    if path.startswith("api/"):
        raise HTTPException(status_code=404)
    static_path = _resolve_static_path(path)                                 # Resolve static file request.
    if static_path:
        return FileResponse(static_path)                                     # Return static asset file.
    index_path = _resolve_static_path("index.html")                          # Resolve SPA index fallback.
    if index_path:
        return FileResponse(index_path)                                      # Return index for client routing.
    raise HTTPException(status_code=404)
