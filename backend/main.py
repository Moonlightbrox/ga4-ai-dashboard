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
from google.api_core import exceptions as gapi_exc
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel, Field

from backend.logs.agent_logging import configure_agent_logging
from backend import session_store
from backend.ai.cloud import analyze_selected_reports
from backend.ai.prompts import (
    AGENT_SYSTEM_PROMPT,
    BUTTON_PROMPTS,
    PROMPT_TEMPLATE_LABELS,
)
from backend.analytics.raw_reports import get_all_core_reports
from backend.data.ga4_schema import CORE_REPORT_DIMENSIONS, CORE_REPORT_METRICS
from backend.data.ga4_service import fetch_ga4_report, ga4_request_context
from backend.data.preprocess import ga4_to_dataframe
from backend import ga4_managed_export


# ------------------------------------------------------------------------------
# Environment setup and application configuration
# ------------------------------------------------------------------------------

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))  # Local env file path for secrets.
load_dotenv(dotenv_path=ENV_PATH)                                            # Load environment variables at startup.

session_store.init_db()                                                      # SQLite backing for OAuth sessions (survives restarts).

configure_agent_logging()                                                    # Structured JSON → stdout + backend/logs/agent.jsonl

app = FastAPI()                                                              # FastAPI app instance for the backend.

OAUTH_SCOPES = [                                                             # GA4 OAuth scopes: reporting + managed BQ export setup.
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics.edit",
    "https://www.googleapis.com/auth/analytics.manage.users",
]
SESSION_COOKIE = "ga4_session"                                               # Cookie name for session tracking.
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30                                   # 30 days; keep cookie across browser restarts.
SESSIONS: dict[str, dict[str, Any]] = {}                                     # In-memory session store keyed by session_id.
STATE_INDEX: dict[str, str] = {}                                             # Map OAuth state -> session_id for callbacks.

# Shown when OAuth tokens are missing, revoked, expired, or lack required scopes (user must use Reconnect).
_RECONNECT_DETAIL = (
    "Google session expired or missing required permissions. "
    "Use Reconnect / Connect GA4 to sign in again (needed after adding new OAuth scopes)."
)


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


# This function loads a session from memory or SQLite and refreshes the cache.
def _get_session_dict(session_id: str) -> dict[str, Any] | None:             # Resolve session payload for a session id.
    if session_id in SESSIONS:
        return SESSIONS[session_id]
    stored = session_store.load_session(session_id)
    if stored is not None:
        SESSIONS[session_id] = stored
        return stored
    return None


# This function persists the current session to SQLite.
def _persist_session(session_id: str) -> None:                               # Persist session payload after mutations.
    session = SESSIONS.get(session_id)
    if session is None:
        return
    session_store.save_session(session_id, session)


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
            max_age=SESSION_COOKIE_MAX_AGE,
        )
        SESSIONS[session_id] = {}                                            # Initialize a new session dict.
        _persist_session(session_id)
    else:
        if _get_session_dict(session_id) is None:
            SESSIONS[session_id] = {}
            _persist_session(session_id)
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


# This function reconstructs credentials, enforces required OAuth scopes, and refreshes when invalid.
def _build_user_credentials(
    session: dict[str, Any], session_id: str | None = None
) -> Credentials | None:  # Restore credentials from session.
    data = session.get("credentials")
    if not data:
        return None
    stored_scopes = set(data.get("scopes") or [])
    if not set(OAUTH_SCOPES).issubset(stored_scopes):
        session.pop("credentials", None)
        if session_id:
            _persist_session(session_id)
        return None
    try:
        credentials = Credentials(**data)
    except (TypeError, ValueError):
        session.pop("credentials", None)
        if session_id:
            _persist_session(session_id)
        return None
    if not credentials.valid:
        if not credentials.refresh_token:
            session.pop("credentials", None)
            if session_id:
                _persist_session(session_id)
            return None
        try:
            credentials.refresh(GoogleAuthRequest())
        except RefreshError:
            session.pop("credentials", None)
            if session_id:
                _persist_session(session_id)
            return None
        session["credentials"] = _credentials_to_dict(credentials)
        if session_id:
            _persist_session(session_id)
    return credentials


# This function enforces that a user is authenticated and has a property selected.
def _require_user_context(request: Request) -> tuple[Credentials, str]:      # Validate session and property.
    session_id = _get_session_id(request)                                    # Read current session id.
    if not session_id:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = _get_session_dict(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    credentials = _build_user_credentials(session, session_id)               # Credentials for GA4 API calls.
    if not credentials:
        raise HTTPException(status_code=401, detail=_RECONNECT_DETAIL)
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
    prompt_template_override: Optional[str] = Field(default=None, max_length=120000)  # Full task prompt; replaces BUTTON_PROMPTS[prompt_key].
    system_prompt_override: Optional[str] = Field(default=None, max_length=200000)   # Replaces AGENT_SYSTEM_PROMPT when non-empty.
    include_agent_trace: bool = Field(default=True)                          # If true, return structured agent events for this run.


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
    _persist_session(session_id)
    STATE_INDEX[state] = session_id                                          # Map state to session for callback.
    return response                                                          # Return the redirect response.


# This endpoint completes OAuth and stores credentials in the session.
@app.get("/api/auth/callback")
def auth_callback(request: Request):                                         # Handle OAuth callback from Google.
    state = request.query_params.get("state")                                # OAuth state from query params.
    session_id = _get_session_id(request) or (STATE_INDEX.get(state) if state else None)
    if not session_id:
        raise HTTPException(status_code=400, detail="Invalid session.")
    session = _get_session_dict(session_id)
    if session is None:
        session = {}
        SESSIONS[session_id] = session
    if state != session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    flow = _get_oauth_flow()                                                 # Rebuild OAuth flow for token exchange.
    flow.fetch_token(authorization_response=str(request.url))                # Exchange auth code for tokens.
    session["credentials"] = _credentials_to_dict(flow.credentials)          # Persist credentials in session.
    session.pop("property_id", None)                                         # Clear any prior property selection.
    session.pop("oauth_state", None)
    _persist_session(session_id)
    response = RedirectResponse(f"{_get_frontend_url()}?connected=1")         # Redirect back to frontend.
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_COOKIE_MAX_AGE,
    )
    return response                                                          # Return redirect with session cookie.


# This endpoint reports whether the session is authenticated.
@app.get("/api/auth/status")
def auth_status(request: Request):                                           # Check current auth status.
    session_id = _get_session_id(request)                                    # Read session id from cookie.
    if not session_id:
        return {"connected": False}                                          # Return false when no session.
    session = _get_session_dict(session_id)
    if session is None:
        return {"connected": False}                                          # Return false when no session.
    credentials = _build_user_credentials(session, session_id)               # Validates scopes + refresh.
    return {"connected": credentials is not None}


# This endpoint lists GA4 properties accessible to the user.
@app.get("/api/ga4/properties")
def list_properties(request: Request):                                       # Fetch available GA4 properties.
    session_id = _get_session_id(request)                                    # Read session id from cookie.
    if not session_id:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = _get_session_dict(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    credentials = _build_user_credentials(session, session_id)               # Build credentials for API calls.
    if not credentials:
        raise HTTPException(status_code=401, detail=_RECONNECT_DETAIL)

    client = AnalyticsAdminServiceClient(credentials=credentials)            # Admin API client for properties.
    try:
        summaries = client.list_account_summaries()                          # Fetch account summaries.
    except gapi_exc.Unauthenticated:
        raise HTTPException(status_code=401, detail=_RECONNECT_DETAIL)
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
    if not session_id:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = _get_session_dict(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session["property_id"] = payload.property_id                             # Store selection for later queries.
    _persist_session(session_id)
    return {"selected": payload.property_id}                                 # Return selection confirmation.


class LinkBigQueryExportRequest(BaseModel):
    streaming_export: bool = False                                           # If true, enable streaming export (higher cost).


# This endpoint runs the managed export flow: user OAuth grants the platform SA on the property, then the SA creates the BigQuery link.
@app.post("/api/ga4/link-bigquery-export")
def link_bigquery_export(
    request: Request,
    payload: LinkBigQueryExportRequest = LinkBigQueryExportRequest(),
) -> dict[str, Any]:
    session_id = _get_session_id(request)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = _get_session_dict(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    credentials = _build_user_credentials(session, session_id)
    if not credentials:
        raise HTTPException(status_code=401, detail=_RECONNECT_DETAIL)
    property_id = session.get("property_id")
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")

    try:
        cfg = ga4_managed_export.get_link_config()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    streaming = payload.streaming_export

    try:
        grant_result = ga4_managed_export.grant_service_account_property_access(
            credentials,
            property_id,
            cfg["service_account_email"],
        )
    except gapi_exc.Unauthenticated:
        raise HTTPException(status_code=401, detail=_RECONNECT_DETAIL)
    except gapi_exc.PermissionDenied:
        raise HTTPException(
            status_code=403,
            detail=ga4_managed_export.PERMISSION_DENIED_GRANT_HELP,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not grant service account on GA4 property: {exc}",
        )

    try:
        link_result = ga4_managed_export.create_managed_bigquery_link(
            property_id,
            cfg["gcp_project_id"],
            cfg["dataset_location"],
            daily_export=True,
            streaming_export=streaming,
        )
    except RuntimeError as exc:
        # ga4_managed_export re-raises PermissionDenied as RuntimeError with message.
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not create BigQuery link: {exc}",
        )

    dataset_hint = f"analytics_{property_id}"
    return {
        "grant": grant_result,
        "bigquery_link": link_result,
        "export_dataset_id_hint": dataset_hint,
        "gcp_project_id": cfg["gcp_project_id"],
        "message": (
            "GA4 will create or use a BigQuery dataset named like "
            f"`{dataset_hint}` in your GCP project. Daily tables may take up to 24–48h to appear."
        ),
    }


# Lists existing BigQuery export links for the selected property (requires service account env).
@app.get("/api/ga4/bigquery-export-status")
def bigquery_export_status(request: Request) -> dict[str, Any]:
    session_id = _get_session_id(request)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = _get_session_dict(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    property_id = session.get("property_id")
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")
    try:
        links = ga4_managed_export.list_bigquery_links_for_property(property_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"property_id": property_id, "bigquery_links": links}


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

# Returns default system and template prompts for the UI editor.
@app.get("/api/ai/prompt-catalog")
def prompt_catalog() -> dict[str, Any]:
    order = (
        "traffic_quality_assessment",
        "conversion_funnel_leakage",
        "landing_page_optimization",
        "insight_basis_explainer",
        "insight_deep_dive_recommendations",
    )
    templates = []
    for key in order:
        if key not in BUTTON_PROMPTS:
            continue
        templates.append(
            {
                "key": key,
                "label": PROMPT_TEMPLATE_LABELS.get(key, key),
                "default_body": BUTTON_PROMPTS[key],
            }
        )
    return {"agent_system_prompt": AGENT_SYSTEM_PROMPT, "templates": templates}


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

    rid = str(uuid4())
    try:
        answer, agent_trace, request_id = analyze_selected_reports(
            selected_reports=reports,
            user_question=req.user_question,
            prompt_key=req.prompt_key,
            prompt_template_override=req.prompt_template_override,
            system_prompt_override=req.system_prompt_override,
            request_id=rid,
            collect_trace=req.include_agent_trace,
        )
    except Exception as exc:                                                 # Handle AI/prompt errors safely.
        raise HTTPException(status_code=500, detail=str(exc))

    out: dict[str, Any] = {"answer": answer, "request_id": request_id}
    if req.include_agent_trace:
        out["agent_trace"] = agent_trace
    return out


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
