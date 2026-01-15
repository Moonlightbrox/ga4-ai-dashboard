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
from backend.data.ga4_service import fetch_ga4_report, ga4_request_context
from backend.data.preprocess import ga4_to_dataframe


ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(dotenv_path=ENV_PATH)

app = FastAPI()

OAUTH_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
SESSION_COOKIE = "ga4_session"
SESSIONS: dict[str, dict[str, Any]] = {}
STATE_INDEX: dict[str, str] = {}


def _parse_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins() or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _df_to_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None:
        return []
    if getattr(df, "empty", False):
        return []
    return df.to_dict(orient="records")


def _records_to_df(rows: list[dict[str, Any]] | None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _get_frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000")


def _get_oauth_flow() -> Flow:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
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
    )


def _get_session_id(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def _ensure_session_id(
    request: Request,
    response: RedirectResponse | JSONResponse,
) -> str:
    session_id = _get_session_id(request)
    if not session_id:
        session_id = str(uuid4())
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            samesite="lax",
        )
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {}
    return session_id


def _credentials_to_dict(credentials: Credentials) -> dict[str, Any]:
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def _build_user_credentials(session: dict[str, Any]) -> Credentials | None:
    data = session.get("credentials")
    if not data:
        return None
    credentials = Credentials(**data)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleAuthRequest())
        session["credentials"] = _credentials_to_dict(credentials)
    return credentials


def _require_user_context(request: Request) -> tuple[Credentials, str]:
    session_id = _get_session_id(request)
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = SESSIONS[session_id]
    credentials = _build_user_credentials(session)
    if not credentials:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    property_id = session.get("property_id")
    if not property_id:
        raise HTTPException(status_code=400, detail="No GA4 property selected.")
    return credentials, property_id


class CustomReportRequest(BaseModel):
    start_date: str
    end_date: str
    metrics: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)


class ReportPayload(BaseModel):
    id: str
    name: str
    description: str
    data: List[Dict[str, Any]] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    selected_reports: List[ReportPayload] = Field(default_factory=list)
    user_question: str
    prompt_key: Optional[str] = None
    coverage_pct: int = 90


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/login")
def auth_login(request: Request):
    state = str(uuid4())
    flow = _get_oauth_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    response = RedirectResponse(authorization_url)
    session_id = _ensure_session_id(request, response)
    SESSIONS[session_id]["oauth_state"] = state
    STATE_INDEX[state] = session_id
    return response


@app.get("/api/auth/callback")
def auth_callback(request: Request):
    state = request.query_params.get("state")
    session_id = _get_session_id(request) or (STATE_INDEX.get(state) if state else None)
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=400, detail="Invalid session.")
    session = SESSIONS[session_id]
    if state != session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    flow = _get_oauth_flow()
    flow.fetch_token(authorization_response=str(request.url))
    session["credentials"] = _credentials_to_dict(flow.credentials)
    session.pop("property_id", None)
    response = RedirectResponse(f"{_get_frontend_url()}?connected=1")
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/api/auth/status")
def auth_status(request: Request):
    session_id = _get_session_id(request)
    if not session_id or session_id not in SESSIONS:
        return {"connected": False}
    session = SESSIONS[session_id]
    return {"connected": bool(session.get("credentials"))}


@app.get("/api/ga4/properties")
def list_properties(request: Request):
    session_id = _get_session_id(request)
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = SESSIONS[session_id]
    credentials = _build_user_credentials(session)
    if not credentials:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")

    client = AnalyticsAdminServiceClient(credentials=credentials)
    summaries = client.list_account_summaries()
    properties = []
    for summary in summaries:
        for prop in summary.property_summaries:
            property_name = prop.property or ""
            property_id = property_name.split("/")[-1] if property_name else ""
            properties.append(
                {
                    "property_id": property_id,
                    "display_name": prop.display_name,
                }
            )

    return {"properties": properties}


class PropertySelection(BaseModel):
    property_id: str


@app.post("/api/ga4/select-property")
def select_property(request: Request, payload: PropertySelection):
    session_id = _get_session_id(request)
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not connected to GA4.")
    session = SESSIONS[session_id]
    session["property_id"] = payload.property_id
    return {"selected": payload.property_id}


@app.get("/api/reports/core")
def get_core_reports(start: str, end: str, request: Request) -> dict[str, Any]:
    credentials, property_id = _require_user_context(request)
    try:
        with ga4_request_context(property_id=property_id, credentials=credentials):
            reports = get_all_core_reports(start, end)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    payload = []
    for report in reports.values():
        payload.append(
            {
                "id": report["id"],
                "name": report["name"],
                "description": report["description"],
                "data": _df_to_records(report.get("data")),
            }
        )

    return {"reports": payload}


@app.post("/api/reports/custom")
def create_custom_report(req: CustomReportRequest, request: Request) -> dict[str, Any]:
    credentials, property_id = _require_user_context(request)
    try:
        with ga4_request_context(property_id=property_id, credentials=credentials):
            response = fetch_ga4_report(
                start_date=req.start_date,
                end_date=req.end_date,
                metrics=req.metrics,
                dimensions=req.dimensions,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    df = ga4_to_dataframe(response)
    return {"data": _df_to_records(df)}


@app.post("/api/ai/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    reports = []
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
            coverage_pct=req.coverage_pct,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"answer": answer}


_FRONTEND_DIST = os.getenv("FRONTEND_DIST")


def _resolve_static_path(path: str) -> str | None:
    if not _FRONTEND_DIST:
        return None
    normalized = os.path.normpath(path.lstrip("/"))
    candidate = os.path.abspath(os.path.join(_FRONTEND_DIST, normalized))
    base = os.path.abspath(_FRONTEND_DIST)
    if os.path.commonpath([candidate, base]) != base:
        return None
    if os.path.isfile(candidate):
        return candidate
    return None


@app.get("/")
def serve_index():
    index_path = _resolve_static_path("index.html")
    if not index_path:
        raise HTTPException(status_code=404)
    return FileResponse(index_path)


@app.get("/{path:path}")
def serve_static(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404)
    static_path = _resolve_static_path(path)
    if static_path:
        return FileResponse(static_path)
    index_path = _resolve_static_path("index.html")
    if index_path:
        return FileResponse(index_path)
    raise HTTPException(status_code=404)
