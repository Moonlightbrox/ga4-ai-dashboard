"""Dataset / table existence + freshness checks.

Cheap status endpoints used by the UI and the agent's ``describe`` action.
Keeps the heavier query logic in :mod:`backend.bigquery.runner` and the SDK
glue in :mod:`backend.bigquery.client`.
"""

from __future__ import annotations

import logging
from typing import Any

from google.api_core import exceptions as gexc

from backend.bigquery.client import (
    _import_bigquery,
    get_bq_client,
    resolve_dataset_ref,
)
from backend.bigquery.runner import resolve_max_bytes


def _collect_tables(client: Any, dataset: Any) -> list[dict[str, Any]]:
    """Lightweight metadata for every table in the dataset.

    Uses only data from ``list_tables`` (no per-table ``get_table``) so the
    status endpoint stays cheap even on properties with months of daily
    ``events_*`` shards.
    """
    tables: list[dict[str, Any]] = []
    for item in client.list_tables(dataset):
        tables.append(
            {
                "name": item.table_id,
                "full_table_id": item.full_table_id,
                "table_type": getattr(item, "table_type", None),
            }
        )
    return tables


def _collect_date_range(
    tables: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Earliest + latest ``events[_intraday]_YYYYMMDD`` suffixes."""
    suffixes: list[str] = []
    for table in tables:
        name = table.get("name", "")
        for prefix in ("events_intraday_", "events_"):
            if name.startswith(prefix):
                suffix = name[len(prefix):]
                if suffix.isdigit() and len(suffix) == 8:
                    suffixes.append(suffix)
                break
    if not suffixes:
        return (None, None)
    suffixes.sort()
    return (suffixes[0], suffixes[-1])


def get_dataset_status(property_id: str) -> dict[str, Any]:
    """Report whether the GA4 export dataset for this property exists.

    Output shape::

        {
            "dataset_ref": "<project>.analytics_<property_id>",
            "exists": bool,
            # only when exists is False:
            "reason": "dataset_missing" | "no_access",
            # only when exists is True:
            "location": "US" | "EU" | ...,
            "tables": [{name, full_table_id, table_type}, ...],
            "earliest_date": "YYYYMMDD" | None,
            "latest_date": "YYYYMMDD" | None,
        }
    """
    dataset_ref = resolve_dataset_ref(property_id)
    client = get_bq_client()

    try:
        dataset = client.get_dataset(dataset_ref)
    except gexc.NotFound:
        return {
            "dataset_ref": dataset_ref,
            "exists": False,
            "reason": "dataset_missing",
        }
    except gexc.Forbidden:
        logging.warning(
            "BigQuery dataset %s exists but the service account lacks access.",
            dataset_ref,
        )
        return {
            "dataset_ref": dataset_ref,
            "exists": False,
            "reason": "no_access",
        }

    tables = _collect_tables(client, dataset)
    earliest, latest = _collect_date_range(tables)

    return {
        "dataset_ref": dataset_ref,
        "exists": True,
        "location": dataset.location,
        "tables": tables,
        "earliest_date": earliest,
        "latest_date": latest,
    }


def list_tables(property_id: str) -> list[dict[str, Any]]:
    """Tables in this property's dataset; empty list if missing/inaccessible."""
    dataset_ref = resolve_dataset_ref(property_id)
    client = get_bq_client()
    try:
        dataset = client.get_dataset(dataset_ref)
    except (gexc.NotFound, gexc.Forbidden):
        return []
    return _collect_tables(client, dataset)


def _list_named_tables(property_id: str, expected: tuple[str, ...]) -> dict[str, Any]:
    """Freshness metadata for a fixed set of tables in the property dataset."""
    dataset_ref = resolve_dataset_ref(property_id)
    client = get_bq_client()

    tables_info: list[dict[str, Any]] = []
    for name in expected:
        full = f"{dataset_ref}.{name}"
        try:
            table = client.get_table(full)
        except gexc.NotFound:
            tables_info.append({"name": name, "exists": False})
            continue
        except gexc.Forbidden as exc:
            raise ValueError(
                f"Access denied listing summary table {name}: {exc}"
            ) from exc
        tables_info.append(
            {
                "name": name,
                "exists": True,
                "last_modified": (
                    table.modified.isoformat()
                    if getattr(table, "modified", None) is not None
                    else None
                ),
                "row_count": int(table.num_rows) if table.num_rows is not None else None,
            }
        )

    return {"dataset_ref": dataset_ref, "tables": tables_info}


def list_web_summary_tables(property_id: str) -> dict[str, Any]:
    """Freshness metadata for the web (``site_*``) summary tables.

    Both ``site_sessions`` and ``site_user_journeys`` should exist after a
    successful ``materialize_web`` run. Missing tables stay in the list with
    ``exists=False`` so the UI can prompt for materialization.
    """
    return _list_named_tables(property_id, ("site_sessions", "site_user_journeys"))


def list_game_summary_tables(property_id: str) -> dict[str, Any]:
    """Freshness metadata for the game (``game_*``) summary tables."""
    from backend.bigquery.materialize_game import GAME_SUMMARY_TABLES

    return _list_named_tables(property_id, GAME_SUMMARY_TABLES)


def list_game_summary_tables_filtered(
    property_id: str,
    physical_by_logical: dict[str, str],
) -> dict[str, Any]:
    """Freshness metadata for a filtered Deep Scan, using suffixed table names.

    ``physical_by_logical`` maps the logical name (e.g. ``game_sessions``) to
    the actual BigQuery table name in the dataset (e.g.
    ``game_sessions_f_abc123def45``). Used when describe runs in
    country/app_version filtered mode.
    """
    dataset_ref = resolve_dataset_ref(property_id)
    client = get_bq_client()

    tables_info: list[dict[str, Any]] = []
    for logical, physical in physical_by_logical.items():
        full = f"{dataset_ref}.{physical}"
        bq_fqn = f"`{dataset_ref}.{physical}`"
        try:
            table = client.get_table(full)
        except gexc.NotFound:
            tables_info.append(
                {
                    "name": logical,
                    "physical_name": physical,
                    "ref": bq_fqn,
                    "exists": False,
                }
            )
            continue
        except gexc.Forbidden as exc:
            raise ValueError(
                f"Access denied listing game table {logical} ({physical}): {exc}"
            ) from exc
        tables_info.append(
            {
                "name": logical,
                "physical_name": physical,
                "ref": bq_fqn,
                "exists": True,
                "last_modified": (
                    table.modified.isoformat()
                    if getattr(table, "modified", None) is not None
                    else None
                ),
                "row_count": int(table.num_rows) if table.num_rows is not None else None,
            }
        )
    from backend.bigquery.materialize_game import GAME_EVENTS_TEST_TABLE

    tables_info.append(
        {
            "name": GAME_EVENTS_TEST_TABLE,
            "physical_name": None,
            "ref": None,
            "exists": False,
            "note": "Not available for country / app_version filtered scan.",
        }
    )
    return {
        "dataset_ref": dataset_ref,
        "scan_mode": "game_filtered_session_slice",
        "tables": tables_info,
    }


def get_game_session_filter_options(property_id: str) -> dict[str, Any]:
    """Distinct ``country`` / ``app_version`` values from ``game_sessions``."""
    from backend.bigquery.materialize_game import GAME_SESSIONS_TABLE

    try:
        dataset_ref = resolve_dataset_ref(property_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    bq = _import_bigquery()
    try:
        client = get_bq_client()
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    # CTE/column names must not reuse "v" for both a table and column: in
    # BigQuery, ORDER BY v inside (SELECT ... FROM v) resolves to the row
    # struct, not the string column.
    sql = f"""
WITH
  countries_cte AS (
    SELECT DISTINCT country AS country_val
    FROM `{dataset_ref}.{GAME_SESSIONS_TABLE}`
    WHERE country IS NOT NULL
  ),
  versions_cte AS (
    SELECT DISTINCT app_version AS version_val
    FROM `{dataset_ref}.{GAME_SESSIONS_TABLE}`
    WHERE app_version IS NOT NULL
  )
SELECT
  (SELECT ARRAY_AGG(country_val ORDER BY country_val) FROM countries_cte) AS countries,
  (SELECT ARRAY_AGG(version_val ORDER BY version_val) FROM versions_cte) AS app_versions
"""
    max_bytes = resolve_max_bytes(None)
    try:
        job = client.query(
            sql, job_config=bq.QueryJobConfig(maximum_bytes_billed=max_bytes)
        )
        row = next(iter(job.result()), None)
    except gexc.NotFound as exc:
        return {
            "ok": False,
            "error": f"game_sessions not found. Run materialize-game first. ({exc})",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    if row is None:
        return {
            "ok": True,
            "dataset_ref": dataset_ref,
            "countries": [],
            "app_versions": [],
        }
    d = dict(row)
    return {
        "ok": True,
        "dataset_ref": dataset_ref,
        "countries": [x for x in (d.get("countries") or []) if x is not None],
        "app_versions": [x for x in (d.get("app_versions") or []) if x is not None],
    }
