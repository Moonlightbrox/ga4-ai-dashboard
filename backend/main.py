"""FastAPI app for the GA4 BigQuery analyst dashboard.

Composition only: this file wires routes to the layered modules
(:mod:`backend.auth`, :mod:`backend.bigquery`, :mod:`backend.agents`). All
business logic lives there; ``main.py`` should stay short enough to read in
one sitting.

Endpoint groups:
    * Auth -- login / callback / status
    * GA4 properties -- list + select
    * BigQuery link -- create / inspect the GA4 -> BigQuery export link
    * BigQuery status / materialize -- dataset + summary table readiness
    * Agents -- run Web / Game analyst, list prompts (read-only)
    * Static -- optional pre-built frontend
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.api_core import exceptions as gapi_exc
from pydantic import BaseModel, Field
from uuid import uuid4

from backend import auth, sessions
from backend.agents import prompts as agent_prompts
from backend.agents.game import run_game_agent
from backend.agents.web import run_web_agent
from backend.bigquery import link as bq_link
from backend.bigquery import materialize_game as bq_materialize_game
from backend.bigquery import materialize_web as bq_materialize_web
from backend.bigquery import runner as bq_runner
from backend.bigquery import status as bq_status
from backend.config import (
    SESSION_COOKIE,
    SESSION_COOKIE_MAX_AGE,
    get_frontend_dist_dir,
    get_frontend_url,
    parse_allowed_origins,
)
from backend.logs.agent_logging import configure_agent_logging


# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------

sessions.init_db()
configure_agent_logging()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins() or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# OAuth login
# ---------------------------------------------------------------------------

@app.get("/api/auth/login")
def auth_login(request: Request):
    state = str(uuid4())
    flow = auth.get_oauth_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    response = RedirectResponse(authorization_url)
    session_id = auth.ensure_session_id(request, response)
    auth.SESSIONS[session_id]["oauth_state"] = state
    auth.persist_session(session_id)
    auth.STATE_INDEX[state] = session_id
    return response


@app.get("/api/auth/callback")
def auth_callback(request: Request):
    state = request.query_params.get("state")
    session_id = auth.get_session_id(request) or (
        auth.STATE_INDEX.get(state) if state else None
    )
    if not session_id:
        raise HTTPException(status_code=400, detail="Invalid session.")
    session = auth.get_session_dict(session_id)
    if session is None:
        session = {}
        auth.SESSIONS[session_id] = session
    if state != session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    flow = auth.get_oauth_flow()
    flow.fetch_token(authorization_response=str(request.url))
    session["credentials"] = auth.credentials_to_dict(flow.credentials)
    session.pop("property_id", None)
    session.pop("oauth_state", None)
    auth.persist_session(session_id)
    response = RedirectResponse(f"{get_frontend_url()}?connected=1")
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_COOKIE_MAX_AGE,
    )
    return response


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, bool]:
    session_id = auth.get_session_id(request)
    if not session_id:
        return {"connected": False}
    session = auth.get_session_dict(session_id)
    if session is None:
        return {"connected": False}
    credentials = auth.build_user_credentials(session, session_id)
    return {"connected": credentials is not None}


# ---------------------------------------------------------------------------
# GA4 property selection (BigQuery dataset is keyed off property_id)
# ---------------------------------------------------------------------------

@app.get("/api/ga4/properties")
def list_properties(request: Request) -> dict[str, Any]:
    credentials, _session_id, _session = auth.require_user(request)
    client = AnalyticsAdminServiceClient(credentials=credentials)
    try:
        summaries = client.list_account_summaries()
    except gapi_exc.Unauthenticated:
        raise HTTPException(status_code=401, detail=auth.RECONNECT_DETAIL)
    properties: list[dict[str, str]] = []
    for summary in summaries:
        for prop in summary.property_summaries:
            property_name = prop.property or ""
            property_id = property_name.split("/")[-1] if property_name else ""
            properties.append(
                {"property_id": property_id, "display_name": prop.display_name}
            )
    return {"properties": properties}


class PropertySelection(BaseModel):
    property_id: str


@app.post("/api/ga4/select-property")
def select_property(
    request: Request,
    payload: PropertySelection,
) -> dict[str, str]:
    _credentials, session_id, session = auth.require_user(request)
    session["property_id"] = payload.property_id
    auth.persist_session(session_id)
    return {"selected": payload.property_id}


# ---------------------------------------------------------------------------
# GA4 -> BigQuery managed export link
# ---------------------------------------------------------------------------

class LinkBigQueryExportRequest(BaseModel):
    streaming_export: bool = False


@app.post("/api/bigquery/link")
def link_bigquery_export(
    request: Request,
    payload: LinkBigQueryExportRequest = LinkBigQueryExportRequest(),
) -> dict[str, Any]:
    credentials, property_id = auth.require_user_property(request)

    try:
        cfg = bq_link.get_link_config()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        grant_result = bq_link.grant_service_account_property_access(
            credentials,
            property_id,
            cfg["service_account_email"],
        )
    except gapi_exc.Unauthenticated:
        raise HTTPException(status_code=401, detail=auth.RECONNECT_DETAIL)
    except gapi_exc.PermissionDenied:
        raise HTTPException(
            status_code=403,
            detail=bq_link.PERMISSION_DENIED_GRANT_HELP,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not grant service account on GA4 property: {exc}",
        )

    # Auto-select every data stream on the property -- GA4 treats an empty
    # ``export_streams`` list as "export nothing" and the events_* tables
    # never appear.
    try:
        export_streams = bq_link.list_data_stream_names(credentials, property_id)
    except gapi_exc.Unauthenticated:
        raise HTTPException(status_code=401, detail=auth.RECONNECT_DETAIL)
    except gapi_exc.PermissionDenied:
        raise HTTPException(
            status_code=403,
            detail=bq_link.PERMISSION_DENIED_GRANT_HELP,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not list GA4 data streams for property {property_id}: {exc}",
        )

    if not export_streams:
        raise HTTPException(
            status_code=400,
            detail=(
                "This GA4 property has no data streams, so there is nothing to "
                "export to BigQuery. Create a web or app stream in GA4 and try again."
            ),
        )

    try:
        link_result = bq_link.create_managed_bigquery_link(
            property_id,
            cfg["gcp_project_id"],
            cfg["dataset_location"],
            daily_export=True,
            streaming_export=payload.streaming_export,
            export_streams=export_streams,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not create BigQuery link: {exc}",
        )

    dataset_hint = f"analytics_{property_id}"
    stream_count = len(export_streams)
    stream_word = "stream" if stream_count == 1 else "streams"

    link_status = link_result.get("status")
    link_streams = link_result.get("export_streams") or []
    streams_updated = bool(link_result.get("export_streams_updated"))
    update_error = link_result.get("export_streams_update_error")

    if link_status == "created":
        link_msg = (
            f"New BigQuery link created with {stream_count} data {stream_word} selected."
        )
    elif streams_updated:
        link_msg = (
            f"Existing BigQuery link patched: added missing data {stream_word} so "
            f"{len(link_streams)} total {'stream is' if len(link_streams) == 1 else 'streams are'} "
            "now exporting."
        )
    elif update_error:
        link_msg = (
            "Existing BigQuery link found but export_streams could NOT be updated -- "
            f"{update_error}. Open GA4 -> Admin -> BigQuery Links and add the missing streams manually."
        )
    elif link_streams:
        link_msg = (
            f"Existing BigQuery link already had all {len(link_streams)} data "
            f"{'stream' if len(link_streams) == 1 else 'streams'} selected; nothing to change."
        )
    else:
        link_msg = (
            "Existing BigQuery link found but no export_streams are configured. "
            "Open GA4 -> Admin -> BigQuery Links and select the streams manually."
        )

    return {
        "grant": grant_result,
        "bigquery_link": link_result,
        "export_streams": export_streams,
        "export_dataset_id_hint": dataset_hint,
        "gcp_project_id": cfg["gcp_project_id"],
        "message": (
            f"{link_msg} Data flows to a BigQuery dataset named like `{dataset_hint}` "
            "in your GCP project. Daily tables may take up to 24-48h to appear; "
            "intraday tables usually show up within an hour."
        ),
    }


@app.get("/api/bigquery/link-status")
def bigquery_link_status(request: Request) -> dict[str, Any]:
    """List existing BigQuery export links for the selected property."""
    _credentials, property_id = auth.require_user_property(request)
    try:
        links = bq_link.list_bigquery_links_for_property(property_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"property_id": property_id, "bigquery_links": links}


# ---------------------------------------------------------------------------
# BigQuery dataset / query (debug + materialization status)
# ---------------------------------------------------------------------------

@app.get("/api/bigquery/status")
def bigquery_dataset_status(request: Request) -> dict[str, Any]:
    """Provisioning status of the GA4 export dataset.

    Reaches into BigQuery (vs the GA4 link resource above) to confirm the
    dataset exists and to list event tables. Used by the UI to tell the user
    whether their export has actually produced ``events_*`` shards yet.
    """
    _credentials, property_id = auth.require_user_property(request)
    try:
        status_payload = bq_status.get_dataset_status(property_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not query BigQuery: {exc}",
        )
    return {"property_id": property_id, **status_payload}


class BigQueryQueryRequest(BaseModel):
    sql: str = Field(..., min_length=1)


@app.post("/api/bigquery/query")
def bigquery_query(
    request: Request,
    payload: BigQueryQueryRequest,
) -> dict[str, Any]:
    """Debug-only endpoint that runs a hand-written SELECT through the validator."""
    _credentials, property_id = auth.require_user_property(request)
    result = bq_runner.run_bq_query(payload.sql, property_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"property_id": property_id, **result}


# ---------------------------------------------------------------------------
# Materialization (web + game summary tables)
# ---------------------------------------------------------------------------

class MaterializeRequest(BaseModel):
    # When omitted, materializers fall back to GA4_MATERIALIZE_DAYS env (default 90).
    days: Optional[int] = Field(default=None, ge=1, le=365)


@app.post("/api/bigquery/materialize-web")
def bigquery_materialize_web_endpoint(
    request: Request,
    payload: MaterializeRequest = MaterializeRequest(),
) -> dict[str, Any]:
    """Build the ``site_*`` Deep Scan summary tables for the selected property."""
    _credentials, property_id = auth.require_user_property(request)
    try:
        result = bq_materialize_web.materialize_all(
            property_id=property_id,
            days=payload.days,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return {"property_id": property_id, **result}


@app.get("/api/bigquery/materialize-web/status")
def bigquery_materialize_web_status(request: Request) -> dict[str, Any]:
    _credentials, property_id = auth.require_user_property(request)
    try:
        status_payload = bq_status.list_web_summary_tables(property_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not list summary tables: {exc}",
        )
    return {"property_id": property_id, **status_payload}


@app.post("/api/bigquery/materialize-game")
def bigquery_materialize_game_endpoint(
    request: Request,
    payload: MaterializeRequest = MaterializeRequest(),
) -> dict[str, Any]:
    """Build the ``game_*`` Deep Scan summary tables for the selected property."""
    _credentials, property_id = auth.require_user_property(request)
    try:
        result = bq_materialize_game.materialize_all_game(
            property_id=property_id,
            days=payload.days,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return {"property_id": property_id, **result}


@app.get("/api/bigquery/materialize-game/status")
def bigquery_materialize_game_status(request: Request) -> dict[str, Any]:
    _credentials, property_id = auth.require_user_property(request)
    try:
        status_payload = bq_status.list_game_summary_tables(property_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not list game summary tables: {exc}",
        )
    return {"property_id": property_id, **status_payload}


@app.get("/api/bigquery/materialize-game/filter-options")
def bigquery_materialize_game_filter_options(request: Request) -> dict[str, Any]:
    """Distinct ``country`` and ``app_version`` from ``game_sessions``."""
    _credentials, property_id = auth.require_user_property(request)
    out = bq_status.get_game_session_filter_options(property_id)
    if not out.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=out.get("error", "Could not load filter options."),
        )
    return {
        "property_id": property_id,
        "dataset_ref": out.get("dataset_ref"),
        "countries": out.get("countries", []),
        "app_versions": out.get("app_versions", []),
    }


# ---------------------------------------------------------------------------
# AI agents (Web Analyst + Game Analyst)
# ---------------------------------------------------------------------------

@app.get("/api/agents/prompts")
def agent_prompt_catalog() -> dict[str, Any]:
    """Read-only prompt catalog for the UI's prompt viewer.

    Two agents, each with one system prompt and one orchestrator template
    (the user message used by the "Deep Scan" button).
    """
    return {
        "agents": [
            {
                "id": "web",
                "label": agent_prompts.WEB_AGENT_LABEL,
                "system_prompt": agent_prompts.WEB_SYSTEM_PROMPT,
                "orchestrator_prompt": agent_prompts.WEB_ORCHESTRATOR_PROMPT,
            },
            {
                "id": "game",
                "label": agent_prompts.GAME_AGENT_LABEL,
                "system_prompt": agent_prompts.GAME_SYSTEM_PROMPT,
                "orchestrator_prompt": agent_prompts.GAME_ORCHESTRATOR_PROMPT,
            },
        ]
    }


class WebAgentRequest(BaseModel):
    # ``deep_scan`` ignores ``user_question`` and runs the orchestrator.
    # ``chat`` requires a non-empty ``user_question`` and uses it verbatim.
    mode: str = Field(default="deep_scan", pattern="^(deep_scan|chat)$")
    user_question: Optional[str] = Field(default=None, max_length=8000)
    include_agent_trace: bool = Field(default=False)


@app.post("/api/agents/web/run")
def run_web_agent_endpoint(
    request: Request,
    req: WebAgentRequest = WebAgentRequest(),
) -> dict[str, Any]:
    _credentials, property_id = auth.require_user_property(request)
    rid = str(uuid4())
    try:
        result = run_web_agent(
            property_id=property_id,
            mode=req.mode,  # type: ignore[arg-type]
            user_question=req.user_question,
            request_id=rid,
            collect_trace=req.include_agent_trace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))

    out: dict[str, Any] = {
        "property_id": property_id,
        "answer": result.answer,
        "request_id": result.request_id,
        "cost_summary": result.cost_summary,
    }
    if req.include_agent_trace:
        out["agent_trace"] = result.trace
    return out


class GameAgentRequest(BaseModel):
    mode: str = Field(default="deep_scan", pattern="^(deep_scan|chat)$")
    user_question: Optional[str] = Field(default=None, max_length=8000)
    include_agent_trace: bool = Field(default=False)
    # Non-empty lists restrict the slice to those session-level values
    # (AND across dimensions). Empty / None on either side = no restriction
    # on that dimension. Both empty = unfiltered.
    filter_countries: Optional[List[str]] = Field(default=None)
    filter_app_versions: Optional[List[str]] = Field(default=None)


@app.post("/api/agents/game/run")
def run_game_agent_endpoint(
    request: Request,
    req: GameAgentRequest = GameAgentRequest(),
) -> dict[str, Any]:
    _credentials, property_id = auth.require_user_property(request)
    rid = str(uuid4())
    fc = [c for c in (req.filter_countries or []) if c and str(c).strip()]
    fa = [v for v in (req.filter_app_versions or []) if v and str(v).strip()]
    try:
        result = run_game_agent(
            property_id=property_id,
            mode=req.mode,  # type: ignore[arg-type]
            user_question=req.user_question,
            filter_countries=fc or None,
            filter_app_versions=fa or None,
            request_id=rid,
            collect_trace=req.include_agent_trace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))

    out: dict[str, Any] = {
        "property_id": property_id,
        "answer": result.answer,
        "request_id": result.request_id,
        "cost_summary": result.cost_summary,
    }
    if req.include_agent_trace:
        out["agent_trace"] = result.trace
    return out


# ---------------------------------------------------------------------------
# Static frontend serving (optional)
# ---------------------------------------------------------------------------

_FRONTEND_DIST = get_frontend_dist_dir()


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
