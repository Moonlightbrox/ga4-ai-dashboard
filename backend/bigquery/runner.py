"""Validator + executor for read-only BigQuery SQL.

The agent tool layer (``backend.agents.tools``) uses ``run_bq_query`` for
every model-generated query. All safety checks live here:
    * SELECT/WITH only.
    * No DML/DDL/scripting keywords (matched on a string-stripped copy so
      identifiers / literals can't false-match).
    * Single statement.
    * Every backtick-quoted reference is fully qualified
      (``project.dataset.table``), the ``project.dataset`` portion equals the
      caller's resolved dataset, and the table name starts with an allowed
      prefix.
    * Hard cap on ``maximum_bytes_billed`` so a runaway scan is rejected by
      BigQuery rather than silently billed.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from google.api_core import exceptions as gexc

from backend.bigquery.client import _import_bigquery, get_bq_client, resolve_dataset_ref


# ---------------------------------------------------------------------------
# Safety limits
# ---------------------------------------------------------------------------

# Hard cap on rows returned to callers.
HARD_ROW_LIMIT = 50

# Truncate string cell values before returning. Prevents one massive cell from
# blowing up JSON size / agent context.
MAX_CELL_CHARS = 120

# Default per-job byte cap when no env override is set.
DEFAULT_MAX_BYTES_BILLED = 100_000_000  # 100 MB

# Allowed table prefixes in the resolved dataset:
#   * events_ / events_intraday_ -- raw GA4 export.
#   * site_ -- summary tables built by ``materialize_web``.
#   * game_ -- summary tables built by ``materialize_game`` (including
#     filtered ``game_*_f_<suffix>`` tables produced by deep-scan filtering).
ALLOWED_TABLE_PREFIXES = (
    "events_intraday_",
    "events_",
    "site_",
    "game_",
)

# Forbidden SQL keywords. Word-boundary matched so identifiers like
# ``inserted_at`` are unaffected.
FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "merge",
    "create", "drop", "alter", "truncate",
    "grant", "revoke",
    "call", "execute", "declare", "begin", "commit", "rollback",
    "load", "export",
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _strip_sql_noise(sql: str) -> str:
    """Replace string literals + comments so keyword scans can't false-match."""
    cleaned = re.sub(r"--[^\n]*", "", sql)
    cleaned = re.sub(r"/\*[\s\S]*?\*/", "", cleaned)
    cleaned = re.sub(r"'(?:[^'\\]|\\.)*'", "''", cleaned)
    cleaned = re.sub(r'"(?:[^"\\]|\\.)*"', '""', cleaned)
    return cleaned


def _extract_backtick_refs(sql: str) -> list[str]:
    return re.findall(r"`([^`]+)`", sql)


def _validate_bq_query(sql: str, dataset_ref: str) -> str | None:
    """Return an error message if rejected, else ``None``.

    See module docstring for the exact rule set.
    """
    if not sql or not isinstance(sql, str):
        return "SQL must be a non-empty string."

    stripped = sql.strip()
    if not stripped:
        return "SQL must be a non-empty string."

    first_token = stripped.split(None, 1)[0].lower()
    if first_token not in ("select", "with"):
        return "Only SELECT or WITH queries are allowed."

    cleaned = _strip_sql_noise(stripped)
    lowered = cleaned.lower()

    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", lowered):
            return f"Forbidden keyword: {kw.upper()}. Only read-only SELECT queries are allowed."

    body = cleaned.rstrip().rstrip(";")
    if ";" in body:
        return "Only a single SQL statement is allowed."

    refs = _extract_backtick_refs(stripped)
    if not refs:
        return (
            "Query must reference tables with backtick-quoted fully-qualified "
            "names, e.g. `project.dataset.table` or `project.dataset.events_*`."
        )

    for ref in refs:
        parts = [p.strip() for p in ref.strip().split(".")]
        if len(parts) != 3:
            return (
                f"Table reference {ref!r} must be fully qualified as "
                "`project.dataset.table`."
            )
        proj_ds = f"{parts[0]}.{parts[1]}"
        table = parts[2]
        if proj_ds != dataset_ref:
            return (
                f"Query must only reference dataset '{dataset_ref}'. "
                f"Found: '{proj_ds}' (from ref {ref!r})."
            )
        if not any(table.startswith(prefix) for prefix in ALLOWED_TABLE_PREFIXES):
            allowed = ", ".join(ALLOWED_TABLE_PREFIXES)
            return (
                f"Table '{table}' must start with one of: {allowed}. "
                "Other GA4 export tables are not exposed to this runner."
            )

    return None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _coerce_cell(value: Any) -> Any:
    """Convert a single BigQuery cell into a JSON-safe scalar with a length cap."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_CELL_CHARS else value[:MAX_CELL_CHARS]
    rendered = str(value)
    return rendered if len(rendered) <= MAX_CELL_CHARS else rendered[:MAX_CELL_CHARS]


def resolve_max_bytes(max_bytes: int | None = None) -> int:
    """Pick the effective ``maximum_bytes_billed`` for a query.

    Precedence: explicit caller arg > env ``GA4_BQ_MAX_BYTES_BILLED`` > default.
    """
    if max_bytes is not None and max_bytes > 0:
        return int(max_bytes)
    raw = os.getenv("GA4_BQ_MAX_BYTES_BILLED", "").strip()
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            logging.warning(
                "GA4_BQ_MAX_BYTES_BILLED=%r is not a positive integer; using default.",
                raw,
            )
    return DEFAULT_MAX_BYTES_BILLED


def run_bq_query(
    sql: str,
    property_id: str,
    *,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    """Validate + execute a read-only BigQuery query for a GA4 property.

    Always returns a JSON-safe dict. On success::

        {
            "row_count": int,
            "total_rows": int | None,
            "truncated": bool,
            "columns": [str, ...],
            "rows": [{col: value, ...}, ...],
            "bytes_billed": int | None,
            "warning": str | None,
        }

    On rejection or runtime failure::

        {"error": "..."}
    """
    try:
        dataset_ref = resolve_dataset_ref(property_id)
    except ValueError as exc:
        return {"error": str(exc)}

    error = _validate_bq_query(sql, dataset_ref)
    if error:
        return {"error": error}

    bq = _import_bigquery()
    try:
        client = get_bq_client()
    except ValueError as exc:
        return {"error": str(exc)}

    job_config = bq.QueryJobConfig(
        maximum_bytes_billed=resolve_max_bytes(max_bytes),
        use_query_cache=True,
    )

    try:
        job = client.query(sql, job_config=job_config)
        rows_iter = job.result()
    except gexc.Forbidden as exc:
        return {"error": f"BigQuery access denied: {getattr(exc, 'message', str(exc))}"}
    except gexc.NotFound as exc:
        return {"error": f"BigQuery resource not found: {getattr(exc, 'message', str(exc))}"}
    except gexc.BadRequest as exc:
        return {"error": f"BigQuery query error: {getattr(exc, 'message', str(exc))}"}
    except Exception as exc:  # noqa: BLE001 - surface any BQ failure to the caller
        return {"error": f"BigQuery error: {exc}"}

    rows: list[dict[str, Any]] = []
    for row in rows_iter:
        if len(rows) >= HARD_ROW_LIMIT:
            break
        rows.append({key: _coerce_cell(value) for key, value in dict(row).items()})

    total_rows = getattr(rows_iter, "total_rows", None)
    truncated = total_rows is not None and total_rows > len(rows)
    if rows:
        columns = list(rows[0].keys())
    else:
        schema = getattr(rows_iter, "schema", None) or []
        columns = [field.name for field in schema]

    warning = None
    if truncated:
        warning = (
            f"Result truncated to {HARD_ROW_LIMIT} rows of {total_rows}. "
            "Add filters or a LIMIT clause to narrow the query."
        )

    return {
        "row_count": len(rows),
        "total_rows": int(total_rows) if total_rows is not None else None,
        "truncated": truncated,
        "columns": columns,
        "rows": rows,
        "bytes_billed": int(job.total_bytes_billed) if job.total_bytes_billed is not None else None,
        "warning": warning,
    }


# ---------------------------------------------------------------------------
# On-demand cost helpers
# ---------------------------------------------------------------------------

# Reference on-demand BigQuery list price per TiB, USD. Override with
# ``GA4_BQ_ON_DEMAND_USD_PER_TB`` for enterprise / regional pricing.
DEFAULT_BQ_ON_DEMAND_USD_PER_TB = 6.25


def resolve_bq_on_demand_usd_per_tb() -> float:
    raw = os.getenv("GA4_BQ_ON_DEMAND_USD_PER_TB", "").strip()
    if not raw:
        return DEFAULT_BQ_ON_DEMAND_USD_PER_TB
    try:
        parsed = float(raw)
        if parsed > 0:
            return parsed
    except ValueError:
        logging.warning(
            "GA4_BQ_ON_DEMAND_USD_PER_TB=%r is not a positive number; using default.",
            raw,
        )
    return DEFAULT_BQ_ON_DEMAND_USD_PER_TB


def estimate_bq_on_demand_usd(bytes_billed: int | None) -> float | None:
    """Approximate on-demand $ cost of ``bytes_billed`` at the configured $/TiB."""
    if bytes_billed is None or bytes_billed < 0:
        return None
    tib = bytes_billed / (1024 ** 4)
    return tib * resolve_bq_on_demand_usd_per_tb()


def enrich_ctas_job_stats(stats: dict[str, Any], max_bytes_billed: int) -> None:
    """Annotate a CTAS stats dict in-place with ``est_cost_usd`` + cap %."""
    bytes_billed = stats.get("bytes_billed")
    if isinstance(bytes_billed, int):
        est = estimate_bq_on_demand_usd(bytes_billed)
        if est is not None:
            stats["est_cost_usd"] = round(est, 6)
        if max_bytes_billed > 0:
            stats["bytes_billed_pct_of_cap"] = round(
                100.0 * bytes_billed / max_bytes_billed, 2
            )
