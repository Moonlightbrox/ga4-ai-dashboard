"""The single agent tool: ``explore_bigquery``.

Both Web Analyst and Game Analyst agents use this one tool. Internally it
dispatches on ``action``:

- ``describe`` -- compact dataset metadata + summary-table readiness. The
  caller (web vs game vs filtered game) controls which summary block is
  attached so each agent only sees the readiness info it cares about.
- ``query`` -- routes through :func:`backend.bigquery.runner.run_bq_query`,
  which validates, caps, and executes the SQL.
"""

from __future__ import annotations

from typing import Any

from backend.bigquery import status as bq_status
from backend.bigquery.runner import run_bq_query


def build_explore_tool_schema() -> dict:
    """Anthropic tool schema for ``explore_bigquery``.

    The validator inside :func:`run_bq_query` owns all safety checks; this
    schema just documents the action surface the model is expected to use.
    """
    return {
        "name": "explore_bigquery",
        "description": (
            "Explore the GA4 BigQuery export for the caller's property. "
            "Use action='describe' to list available tables, the covered date "
            "range, and the freshness of the summary tables this agent reads. "
            "Use action='query' to run BigQuery Standard SQL against the "
            "caller's dataset. Queries must use backtick-quoted "
            "`project.dataset.table` references."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["describe", "query"],
                },
                "query": {
                    "type": "string",
                    "description": (
                        "BigQuery Standard SQL SELECT. Required when action='query'."
                    ),
                },
                "intent": {
                    "type": "string",
                    "description": "Brief reason for this call (used in logs).",
                },
            },
            "required": ["action"],
        },
    }


def _compact_dataset_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop the per-shard ``tables`` list out of a dataset status payload.

    For properties with months of daily GA4 exports the full list balloons to
    thousands of ``events_YYYYMMDD`` entries -- once that is in the agent
    context, every subsequent step re-sends it and the input-token rate-limit
    budget evaporates. We keep ``dataset_ref``, ``location``, the date range,
    and a capped preview of non-event tables; the agent only needs the date
    range + ``_TABLE_SUFFIX`` to plan ``events_*`` queries.
    """
    if not isinstance(payload, dict):
        return payload
    tables = payload.get("tables")
    if not isinstance(tables, list):
        return dict(payload)

    event_shard_count = 0
    intraday_count = 0
    other_tables: list[str] = []
    for tbl in tables:
        if not isinstance(tbl, dict):
            continue
        name = str(tbl.get("name", ""))
        if name.startswith("events_intraday_"):
            intraday_count += 1
        elif name.startswith("events_") and name[len("events_"):].isdigit():
            event_shard_count += 1
        else:
            other_tables.append(name)

    compact = {k: v for k, v in payload.items() if k != "tables"}
    compact["event_tables_count"] = event_shard_count
    if intraday_count:
        compact["event_intraday_tables_count"] = intraday_count
    if other_tables:
        compact["other_tables"] = other_tables[:25]
        if len(other_tables) > 25:
            compact["other_tables_truncated"] = True
    return compact


def _bq_describe(
    property_id: str,
    *,
    include_web_summary: bool = False,
    include_game_summary: bool = False,
    game_filtered_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``describe`` payload the agent sees on action='describe'.

    ``include_web_summary`` adds a ``summary_tables`` block with freshness for
    ``site_*``. ``include_game_summary`` adds ``game_summary_tables`` for the
    ``game_*`` tables (or the filtered slice when ``game_filtered_scan`` is
    set). Each agent passes only the flag it needs so the response stays
    small.
    """
    try:
        payload = bq_status.get_dataset_status(property_id)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - forward to the agent as a tool error
        return {"error": f"BigQuery describe failed: {exc}"}

    effective = (
        _compact_dataset_status(payload)
        if isinstance(payload, dict) and payload.get("exists") is True
        else payload
    )

    out: dict[str, Any] = {"property_id": property_id, **effective}

    if include_web_summary:
        try:
            out["summary_tables"] = bq_status.list_web_summary_tables(property_id)
        except ValueError as exc:
            out["summary_tables"] = {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            out["summary_tables"] = {"error": f"list_web_summary_tables failed: {exc}"}

    if include_game_summary:
        phys = (
            game_filtered_scan.get("physical_tables")
            if isinstance(game_filtered_scan, dict)
            else None
        )
        if phys:
            try:
                out["game_summary_tables"] = (
                    bq_status.list_game_summary_tables_filtered(property_id, phys)
                )
                flt = game_filtered_scan.get("filter") if game_filtered_scan else None
                if isinstance(flt, dict):
                    out["game_summary_tables"]["filter"] = flt
            except ValueError as exc:
                out["game_summary_tables"] = {"error": str(exc)}
            except Exception as exc:  # noqa: BLE001
                out["game_summary_tables"] = {
                    "error": f"list_game_summary_tables_filtered failed: {exc}"
                }
        else:
            try:
                out["game_summary_tables"] = bq_status.list_game_summary_tables(
                    property_id
                )
            except ValueError as exc:
                out["game_summary_tables"] = {"error": str(exc)}
            except Exception as exc:  # noqa: BLE001
                out["game_summary_tables"] = {
                    "error": f"list_game_summary_tables failed: {exc}"
                }

    return out


def explore_bigquery(
    tool_input: dict,
    property_id: str,
    *,
    include_web_summary: bool = False,
    include_game_summary: bool = False,
    game_filtered_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch one ``explore_bigquery`` tool call.

    Always returns a JSON-serialisable dict. Errors come back as
    ``{"error": "..."}`` so the runner can forward them to the model
    unchanged for self-correction.
    """
    if not isinstance(tool_input, dict):
        return {"error": "Invalid tool input."}
    action = tool_input.get("action")
    if action == "describe":
        return _bq_describe(
            property_id,
            include_web_summary=include_web_summary,
            include_game_summary=include_game_summary,
            game_filtered_scan=game_filtered_scan,
        )
    if action == "query":
        query = tool_input.get("query")
        if not query:
            return {"error": "query is required when action='query'."}
        return run_bq_query(query, property_id)
    return {"error": f"Unsupported action: {action}."}
