"""Game Analyst AI entrypoint.

Reads the ``game_*`` summary tables built by
:mod:`backend.bigquery.materialize_game` and produces either:

- a Deep Scan retention/gameplay report (``mode='deep_scan'``), or
- a free-form chat answer to ``user_question`` (``mode='chat'``).

Both modes optionally run against a country / app_version slice. When a
filter is provided, :func:`materialize_game_filtered_for_deep_scan` rebuilds
``game_user_journeys`` and ``game_levels`` from just that slice into
suffixed tables (``game_*_f_<id>``); the system prompt is augmented to point
the agent at those tables only, and the temp tables are dropped on exit.
"""

from __future__ import annotations

from typing import Any, Literal

from backend.agents.prompts import (
    GAME_ORCHESTRATOR_PROMPT,
    GAME_SYSTEM_PROMPT,
    game_filtered_system_addendum,
)
from backend.agents.runner import AgentResult, build_user_message, run_agent
from backend.agents.tools import explore_bigquery
from backend.bigquery.materialize_game import (
    drop_game_filtered_scan_tables,
    materialize_game_filtered_for_deep_scan,
)
from backend.logs.agent_logging import log_agent_event, log_agent_warning


GameMode = Literal["deep_scan", "chat"]


def _build_filtered_scan(
    property_id: str,
    countries: list[str] | None,
    app_versions: list[str] | None,
) -> dict[str, Any] | None:
    """Build (or skip) a country / app_version slice before the run.

    Returns the materialize result dict on success (used by the runner to
    aim ``describe`` at the suffixed tables and the system addendum to name
    them), ``None`` when no filter was requested. Build failures surface as
    a result with ``ok=False`` -- the caller decides whether to abort.
    """
    has_filter = bool(countries) or bool(app_versions)
    if not has_filter:
        return None
    return materialize_game_filtered_for_deep_scan(
        property_id,
        filter_countries=list(countries or []),
        filter_app_versions=list(app_versions or []),
    )


def run_game_agent(
    *,
    property_id: str,
    mode: GameMode,
    user_question: str | None = None,
    filter_countries: list[str] | None = None,
    filter_app_versions: list[str] | None = None,
    request_id: str | None = None,
    collect_trace: bool = True,
) -> AgentResult:
    """Run the Game Analyst AI for a property.

    See module docstring for filter behaviour. The function never raises on
    a filter build failure -- it returns an :class:`AgentResult` whose
    ``answer`` describes the failure so the API layer / UI can surface it.
    """
    if mode == "deep_scan":
        body = GAME_ORCHESTRATOR_PROMPT
    elif mode == "chat":
        body = (user_question or "").strip()
        if not body:
            raise ValueError("Game Analyst chat requires a non-empty question.")
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported game mode: {mode!r}")

    gscan: dict[str, Any] | None = None
    table_names_to_drop: list[str] = []
    has_filter = bool(filter_countries) or bool(filter_app_versions)
    if has_filter:
        try:
            gscan = _build_filtered_scan(
                property_id, filter_countries, filter_app_versions
            )
        except Exception as exc:  # noqa: BLE001
            log_agent_warning(
                "game_agent_filtered_build_exception",
                property_id=property_id,
                error=str(exc),
            )
            gscan = {"ok": False, "error": str(exc)}

        if not (isinstance(gscan, dict) and gscan.get("ok")):
            err = (
                gscan.get("error")
                if isinstance(gscan, dict)
                else "Filtered materialization failed."
            )
            return AgentResult(
                answer=(
                    "Could not build the filtered Game Deep Scan slice "
                    f"(country / app_version):\n\n{err}\n\n"
                    "Try again without a filter or fix the underlying error."
                ),
                trace=[],
                request_id=request_id or "",
                cost_summary={
                    "bigquery": {
                        "query_count": 0,
                        "total_bytes_billed": 0,
                        "total_est_cost_usd": None,
                        "max_bytes_billed_cap": 0,
                        "usd_per_tb_assumed": 0.0,
                        "per_query": [],
                    },
                    "note": "Filtered build failed before the agent ran.",
                },
            )
        table_names_to_drop = list(gscan.get("tables_built") or [])

    system_prompt = GAME_SYSTEM_PROMPT
    if gscan and gscan.get("ok") and gscan.get("fqn_by_logical"):
        flt = gscan.get("filter") or {}
        system_prompt = system_prompt + game_filtered_system_addendum(
            gscan["fqn_by_logical"],
            list(flt.get("countries") or []),
            list(flt.get("app_versions") or []),
        )

    def dispatch(params: dict[str, Any]) -> dict[str, Any]:
        return explore_bigquery(
            params,
            property_id,
            include_game_summary=True,
            game_filtered_scan=gscan if gscan and gscan.get("ok") else None,
        )

    try:
        return run_agent(
            agent_label="game_agent",
            system_prompt=system_prompt,
            user_message=build_user_message(body),
            dispatch=dispatch,
            request_id=request_id,
            collect_trace=collect_trace,
        )
    finally:
        # Always clean up the filtered slice's temp tables, even on raise.
        if table_names_to_drop:
            try:
                drop_game_filtered_scan_tables(property_id, table_names_to_drop)
                log_agent_event(
                    "game_agent_filtered_temp_tables_dropped",
                    property_id=property_id,
                    table_count=len(table_names_to_drop),
                )
            except Exception as exc:  # noqa: BLE001
                log_agent_warning(
                    "game_agent_filtered_temp_tables_drop_failed",
                    property_id=property_id,
                    error=str(exc),
                )
