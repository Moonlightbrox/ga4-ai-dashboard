"""Build the site_* summary tables used by the Deep Scan AI agent.

Produces two tables in the property's GA4 export dataset:

- ``site_sessions`` -- one row per session, with ordered event/page sequences,
  per-session attribution, and outcome flags. Built directly from the raw
  ``events_*`` shards; this is the only expensive scan in the pipeline.

- ``site_user_journeys`` -- one row per ``user_pseudo_id`` with a ``user_group``
  label (``active_buyer``, ``active_non_buyer``, ``churned_buyer``,
  ``churned_non_buyer``, ``new``) and aggregated journey features. Built from
  ``site_sessions``, not from raw events, so it stays cheap.

Cost controls:
    * Window defaults to 90 days (``GA4_MATERIALIZE_DAYS``), clamped to the
      earliest available event table.
    * Every job runs with ``maximum_bytes_billed`` from
      ``GA4_MATERIALIZE_MAX_BYTES`` (default 5 GB) so a runaway scan is
      refused by BigQuery rather than silently billed.
    * ``use_query_cache`` is off because the destination is CREATE OR REPLACE;
      cache doesn't help and we want to know the real bytes billed.

The module intentionally does not call the AI layer; phase 2's agent reads
these tables via the existing ``explore_bigquery`` path.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from typing import Any

from google.api_core import exceptions as gexc

from backend.bigquery import status as bq_status
from backend.bigquery.client import (
    _import_bigquery,
    get_bq_client,
    resolve_dataset_ref,
)
# Cost helpers live next to the SQL runner so the AI tool layer can use them
# without pulling the whole materializer module. Re-exported here to keep
# ``materialize_game`` (and any external callers) from having to know about the
# split.
from backend.bigquery.runner import (  # noqa: F401 - re-exports for backwards compat
    enrich_ctas_job_stats,
    estimate_bq_on_demand_usd,
    resolve_bq_on_demand_usd_per_tb,
)
from backend.logs.agent_logging import log_agent_event, log_agent_warning


DEFAULT_WINDOW_DAYS = 90
DEFAULT_MATERIALIZE_MAX_BYTES = 5_000_000_000  # 5 GB

DEFAULT_CHURN_CUTOFF_DAYS = 30  # "churned" if last_seen is older than this.
DEFAULT_NEW_CUTOFF_DAYS = 7  # "new" if first_seen is within this many days of w_end.

SESSIONS_TABLE = "site_sessions"
USER_JOURNEYS_TABLE = "site_user_journeys"
SUMMARY_TABLES = (SESSIONS_TABLE, USER_JOURNEYS_TABLE)


# ---------------------------------------------------------------------------
# Env / window resolution
# ---------------------------------------------------------------------------

def _resolve_window_days(days: int | None) -> int:
    """Pick the effective number of days for the materialization window.

    Precedence: explicit caller arg > env ``GA4_MATERIALIZE_DAYS`` > default.
    """
    if days is not None and int(days) > 0:
        return int(days)
    raw = os.getenv("GA4_MATERIALIZE_DAYS", "").strip()
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            logging.warning(
                "GA4_MATERIALIZE_DAYS=%r is not a positive integer; using default.",
                raw,
            )
    return DEFAULT_WINDOW_DAYS


def _resolve_cutoffs(window_days: int) -> tuple[int, int]:
    """Return ``(new_cutoff_days, churn_cutoff_days)`` for the current window.

    Precedence: env vars > defaults, then both values are clamped so they make
    sense relative to ``window_days``. In particular, ``new_cutoff`` is forced
    below ``churn_cutoff`` so the two groups don't collapse into each other,
    and ``churn_cutoff`` is capped at ``window_days - 1`` so at least one day
    of "churned" history is possible on short histories.
    """
    def _env_int(name: str, default: int) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            parsed = int(raw)
            return parsed if parsed > 0 else default
        except ValueError:
            logging.warning("%s=%r is not a positive integer; using default.", name, raw)
            return default

    new_cutoff = _env_int("GA4_NEW_CUTOFF_DAYS", DEFAULT_NEW_CUTOFF_DAYS)
    churn_cutoff = _env_int("GA4_CHURN_CUTOFF_DAYS", DEFAULT_CHURN_CUTOFF_DAYS)
    max_churn = max(1, window_days - 1)
    if churn_cutoff > max_churn:
        churn_cutoff = max_churn
    if new_cutoff >= churn_cutoff:
        new_cutoff = max(1, churn_cutoff // 3)
    return new_cutoff, churn_cutoff


def _resolve_materialize_max_bytes() -> int:
    """Effective ``maximum_bytes_billed`` for CTAS materialization jobs.

    Distinct from :func:`backend.bigquery.runner.resolve_max_bytes` -- that one
    caps the small AI agent queries (default 100 MB), while this one caps the
    expensive raw ``events_*`` scans the materializer runs (default 5 GB).
    Different env knob (``GA4_MATERIALIZE_MAX_BYTES`` vs
    ``GA4_BQ_MAX_BYTES_BILLED``) keeps the two budgets independent.
    """
    raw = os.getenv("GA4_MATERIALIZE_MAX_BYTES", "").strip()
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            logging.warning(
                "GA4_MATERIALIZE_MAX_BYTES=%r is not a positive integer; using default.",
                raw,
            )
    return DEFAULT_MATERIALIZE_MAX_BYTES


def _parse_yyyymmdd(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _suffix(d: date) -> str:
    return d.strftime("%Y%m%d")


def _resolve_window(property_id: str, days: int | None = None) -> tuple[date, date]:
    """Return ``(w_start, w_end)`` aligned to the caller's available event tables.

    ``w_end`` is the latest ``events_YYYYMMDD`` table the dataset has. ``w_start``
    is ``w_end - (window_days - 1)`` clamped up to the earliest available
    event table so we never reference a suffix that doesn't exist.
    """
    dataset_status = bq_status.get_dataset_status(property_id)
    if not dataset_status.get("exists"):
        raise ValueError(
            f"Dataset for property {property_id} is not ready "
            f"(reason={dataset_status.get('reason')})."
        )
    latest = dataset_status.get("latest_date")
    if not latest:
        raise ValueError(
            "No events_* tables found in dataset yet. The GA4 BigQuery export "
            "typically takes 24-72 hours after linking before daily event "
            "tables appear."
        )
    w_end = _parse_yyyymmdd(latest)
    w_start = w_end - timedelta(days=_resolve_window_days(days) - 1)
    earliest = dataset_status.get("earliest_date")
    if earliest:
        e = _parse_yyyymmdd(earliest)
        if w_start < e:
            w_start = e
    if w_start > w_end:
        raise ValueError(
            f"Computed empty window {w_start}..{w_end}; dataset may not have "
            "enough event data to materialize."
        )
    return w_start, w_end


# ---------------------------------------------------------------------------
# SQL builders
# ---------------------------------------------------------------------------
#
# Both SQL strings use named query parameters (``@w_start_suffix``,
# ``@w_end_suffix``, ``@w_end``) and reference only the caller's dataset via
# fully-qualified backtick names. The BigQuery validator in
# ``backend.bigquery.runner._validate_bq_query`` is not applied here because
# these aren't AI-issued queries -- they're fixed CTAS templates we control.

def _build_sessions_sql(dataset_ref: str) -> str:
    """CTAS for ``site_sessions``. Scans ``events_*`` once between the window suffixes.

    v1 uses only ``traffic_source.{source,medium,name}`` for attribution. In the
    GA4 BigQuery export this struct is USER-LEVEL (first-touch acquisition),
    so it repeats on every session of a user -- session-level ``source`` here
    means "where the user was originally acquired," not "where this session
    came from." ``collected_traffic_source`` would give per-session / per-event
    attribution but is only present on exports since ~April 2023; we can add
    a schema-detection fallback when we need that fidelity.
    """
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{SESSIONS_TABLE}` AS
WITH events AS (
  SELECT
    user_pseudo_id,
    event_name,
    event_timestamp,
    PARSE_DATE('%Y%m%d', event_date) AS event_date_parsed,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location') AS page_location,
    device.category AS device_category,
    geo.country AS country,
    traffic_source.source AS src,
    traffic_source.medium AS med,
    traffic_source.name AS cmp,
    ecommerce.purchase_revenue AS purchase_revenue
  FROM `{dataset_ref}.events_*`
  WHERE _TABLE_SUFFIX BETWEEN @w_start_suffix AND @w_end_suffix
    AND user_pseudo_id IS NOT NULL
),
tagged AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY user_pseudo_id, ga_session_id
      ORDER BY event_timestamp
    ) AS event_rank
  FROM events
  WHERE ga_session_id IS NOT NULL
)
SELECT
  TO_HEX(MD5(CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING)))) AS session_id,
  user_pseudo_id,
  MIN(event_date_parsed) AS session_date,
  TIMESTAMP_MICROS(MIN(event_timestamp)) AS session_start_ts,
  MIN(IF(event_rank = 1, src, NULL)) AS source,
  MIN(IF(event_rank = 1, med, NULL)) AS medium,
  MIN(IF(event_rank = 1, cmp, NULL)) AS campaign,
  MIN(IF(event_rank = 1, device_category, NULL)) AS device_category,
  MIN(IF(event_rank = 1, country, NULL)) AS country,
  MIN(IF(event_rank = 1, page_location, NULL)) AS landing_page,
  COUNT(*) AS event_count,
  COUNTIF(event_name = 'page_view') AS pageview_count,
  CAST(SAFE_DIVIDE(MAX(event_timestamp) - MIN(event_timestamp), 1000000) AS INT64) AS duration_seconds,
  ARRAY_AGG(event_name ORDER BY event_timestamp LIMIT 15) AS event_sequence,
  ARRAY_AGG(
    COALESCE(REGEXP_EXTRACT(page_location, r'^https?://[^/]+(/[^?#]*)'), page_location, '')
    ORDER BY event_timestamp LIMIT 15
  ) AS page_sequence,
  LOGICAL_OR(event_name = 'view_search_results') AS had_search,
  LOGICAL_OR(event_name IN ('view_item', 'view_item_details')) AS had_product_view,
  LOGICAL_OR(event_name = 'add_to_cart') AS had_add_to_cart,
  LOGICAL_OR(event_name = 'begin_checkout') AS had_begin_checkout,
  LOGICAL_OR(event_name = 'purchase') AS converted_this_session,
  CAST(
    SUM(CASE WHEN event_name = 'purchase' THEN IFNULL(purchase_revenue, 0) ELSE 0 END)
    AS NUMERIC
  ) AS revenue
FROM tagged
GROUP BY user_pseudo_id, ga_session_id
"""


def _build_user_journeys_sql(
    dataset_ref: str,
    new_cutoff_days: int,
    churn_cutoff_days: int,
) -> str:
    """CTAS for ``site_user_journeys``. Aggregates ``site_sessions`` -- cheap.

    ``new_cutoff_days`` and ``churn_cutoff_days`` are baked into the CASE
    expression as literals (not query parameters) because BigQuery doesn't
    allow parameterizing ``INTERVAL`` literals. They are resolved upstream
    via :func:`_resolve_cutoffs` from env vars + the effective window.
    """
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{USER_JOURNEYS_TABLE}` AS
WITH ranked_sessions AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY session_start_ts) AS session_rank_asc,
    ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY session_start_ts DESC) AS session_rank_desc
  FROM `{dataset_ref}.{SESSIONS_TABLE}`
),
session_agg AS (
  SELECT
    user_pseudo_id,
    MIN(session_date) AS first_seen_date,
    MAX(session_date) AS last_seen_date,
    COUNT(*) AS total_sessions,
    SUM(event_count) AS total_events,
    SUM(pageview_count) AS total_pageviews,
    COUNTIF(converted_this_session) AS total_purchases,
    CAST(SUM(revenue) AS NUMERIC) AS total_revenue,
    MIN(IF(converted_this_session, session_date, NULL)) AS first_purchase_date,
    LOGICAL_OR(had_search) AS had_search,
    LOGICAL_OR(had_product_view) AS had_product_view,
    LOGICAL_OR(had_add_to_cart) AS had_add_to_cart,
    COUNTIF(had_add_to_cart AND NOT converted_this_session) AS cart_abandon_count,
    MIN(IF(session_rank_asc = 1, source, NULL)) AS first_touch_source,
    MIN(IF(session_rank_asc = 1, medium, NULL)) AS first_touch_medium,
    MIN(IF(session_rank_asc = 1, device_category, NULL)) AS first_touch_device,
    MIN(IF(session_rank_desc = 1, source, NULL)) AS last_touch_source,
    MIN(IF(session_rank_desc = 1, medium, NULL)) AS last_touch_medium,
    APPROX_TOP_COUNT(device_category, 1)[OFFSET(0)].value AS primary_device,
    APPROX_TOP_COUNT(country, 1)[OFFSET(0)].value AS primary_country,
    APPROX_TOP_COUNT(
      CASE
        WHEN EXTRACT(HOUR FROM session_start_ts) BETWEEN 5 AND 11 THEN 'morning'
        WHEN EXTRACT(HOUR FROM session_start_ts) BETWEEN 12 AND 17 THEN 'afternoon'
        WHEN EXTRACT(HOUR FROM session_start_ts) BETWEEN 18 AND 22 THEN 'evening'
        ELSE 'night'
      END,
      1
    )[OFFSET(0)].value AS time_of_day_mode,
    COUNTIF(EXTRACT(DAYOFWEEK FROM session_start_ts) IN (1, 7)) AS weekend_sessions,
    COUNTIF(EXTRACT(DAYOFWEEK FROM session_start_ts) NOT IN (1, 7)) AS weekday_sessions
  FROM ranked_sessions
  GROUP BY user_pseudo_id
),
best_session AS (
  SELECT user_pseudo_id, event_sequence AS top_event_sequence
  FROM `{dataset_ref}.{SESSIONS_TABLE}`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY user_pseudo_id
    ORDER BY event_count DESC, session_start_ts DESC
  ) = 1
)
SELECT
  s.user_pseudo_id,
  CASE
    WHEN s.first_seen_date > DATE_SUB(@w_end, INTERVAL {new_cutoff_days} DAY) THEN 'new'
    WHEN s.total_purchases > 0
         AND s.last_seen_date > DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY)
      THEN 'active_buyer'
    WHEN s.total_purchases > 0 THEN 'churned_buyer'
    WHEN s.last_seen_date > DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY)
      THEN 'active_non_buyer'
    ELSE 'churned_non_buyer'
  END AS user_group,
  s.first_seen_date,
  s.last_seen_date,
  DATE_DIFF(s.last_seen_date, s.first_seen_date, DAY) AS days_active_span,
  s.total_sessions,
  s.total_events,
  s.total_pageviews,
  s.total_purchases,
  s.total_revenue,
  s.first_purchase_date,
  CASE WHEN s.first_purchase_date IS NOT NULL
       THEN DATE_DIFF(s.first_purchase_date, s.first_seen_date, DAY)
       ELSE NULL END AS days_to_first_purchase,
  s.first_touch_source,
  s.first_touch_medium,
  s.first_touch_device,
  s.last_touch_source,
  s.last_touch_medium,
  s.primary_device,
  s.primary_country,
  s.time_of_day_mode,
  CASE
    WHEN s.weekend_sessions = 0 THEN 'weekday'
    WHEN s.weekday_sessions = 0 THEN 'weekend'
    ELSE 'mixed'
  END AS weekday_weekend,
  s.had_search,
  s.had_product_view,
  s.had_add_to_cart,
  s.cart_abandon_count,
  b.top_event_sequence,
  s.first_seen_date <= DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY) AS is_eligible_for_churn
FROM session_agg s
LEFT JOIN best_session b USING (user_pseudo_id)
"""


# ---------------------------------------------------------------------------
# Job runner
# ---------------------------------------------------------------------------

def _run_ctas(
    client: Any,
    sql: str,
    job_config: Any,
    dataset_ref: str,
    table_name: str,
) -> dict[str, Any]:
    """Execute a single CREATE OR REPLACE TABLE job and return its stats."""
    t0 = time.monotonic()
    job = client.query(sql, job_config=job_config)
    job.result()  # block until the table is written
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    try:
        table = client.get_table(f"{dataset_ref}.{table_name}")
        row_count = int(table.num_rows) if table.num_rows is not None else None
    except Exception:  # noqa: BLE001 - row count is nice-to-have, not critical
        row_count = None
    return {
        "table": table_name,
        "rows": row_count,
        "bytes_billed": int(job.total_bytes_billed) if job.total_bytes_billed is not None else None,
        "bytes_processed": int(job.total_bytes_processed) if job.total_bytes_processed is not None else None,
        "elapsed_ms": elapsed_ms,
    }


def materialize_all(
    property_id: str,
    days: int | None = None,
) -> dict[str, Any]:
    """Build ``site_sessions`` and ``site_user_journeys`` for one property.

    Returns a dict shaped like::

        {
            "ok": True,
            "dataset_ref": "<project>.analytics_<property_id>",
            "window": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "days": N},
            "tables": [
                {"table": "site_sessions", "rows": ..., "bytes_billed": ..., "elapsed_ms": ...},
                {"table": "site_user_journeys", ...},
            ],
            "total_bytes_billed": N,
        }

    On the first failure, returns ``{"ok": False, "error": "...", ...}`` and
    stops -- we don't try to build ``site_user_journeys`` if ``site_sessions``
    didn't land, because the journeys build reads from it.
    """
    bq = _import_bigquery()

    try:
        dataset_ref = resolve_dataset_ref(property_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        w_start, w_end = _resolve_window(property_id, days)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "dataset_ref": dataset_ref}

    try:
        client = get_bq_client()
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "dataset_ref": dataset_ref}

    max_bytes = _resolve_materialize_max_bytes()
    window_days = (w_end - w_start).days + 1
    window_info = {
        "start": str(w_start),
        "end": str(w_end),
        "days": window_days,
    }
    new_cutoff_days, churn_cutoff_days = _resolve_cutoffs(window_days)
    cutoffs_info = {
        "new_cutoff_days": new_cutoff_days,
        "churn_cutoff_days": churn_cutoff_days,
    }

    log_agent_event(
        "materialize_run_start",
        property_id=property_id,
        dataset_ref=dataset_ref,
        window=window_info,
        cutoffs=cutoffs_info,
        max_bytes_billed=max_bytes,
    )

    results: list[dict[str, Any]] = []

    sessions_config = bq.QueryJobConfig(
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
        query_parameters=[
            bq.ScalarQueryParameter("w_start_suffix", "STRING", _suffix(w_start)),
            bq.ScalarQueryParameter("w_end_suffix", "STRING", _suffix(w_end)),
        ],
    )
    try:
        sessions_stats = _run_ctas(
            client,
            _build_sessions_sql(dataset_ref),
            sessions_config,
            dataset_ref,
            SESSIONS_TABLE,
        )
    except gexc.Forbidden as exc:
        msg = (
            f"Permission denied building {SESSIONS_TABLE}. The platform service "
            f"account needs bigquery.dataEditor on {dataset_ref}. "
            f"({getattr(exc, 'message', str(exc))})"
        )
        log_agent_warning("materialize_run_end", ok=False, error=msg)
        return {
            "ok": False,
            "error": msg,
            "dataset_ref": dataset_ref,
            "window": window_info,
        }
    except gexc.BadRequest as exc:
        msg = f"BigQuery rejected {SESSIONS_TABLE} build: {getattr(exc, 'message', str(exc))}"
        log_agent_warning("materialize_run_end", ok=False, error=msg)
        return {
            "ok": False,
            "error": msg,
            "dataset_ref": dataset_ref,
            "window": window_info,
        }
    except Exception as exc:  # noqa: BLE001 - surface any BQ failure to caller
        msg = f"Failed building {SESSIONS_TABLE}: {exc}"
        log_agent_warning("materialize_run_end", ok=False, error=msg)
        return {
            "ok": False,
            "error": msg,
            "dataset_ref": dataset_ref,
            "window": window_info,
        }
    results.append(sessions_stats)
    log_agent_event("materialize_table_built", **sessions_stats)

    journeys_config = bq.QueryJobConfig(
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
        query_parameters=[
            bq.ScalarQueryParameter("w_end", "DATE", w_end),
        ],
    )
    try:
        journeys_stats = _run_ctas(
            client,
            _build_user_journeys_sql(
                dataset_ref,
                new_cutoff_days=new_cutoff_days,
                churn_cutoff_days=churn_cutoff_days,
            ),
            journeys_config,
            dataset_ref,
            USER_JOURNEYS_TABLE,
        )
    except Exception as exc:  # noqa: BLE001
        msg = f"Failed building {USER_JOURNEYS_TABLE}: {exc}"
        log_agent_warning(
            "materialize_run_end",
            ok=False,
            error=msg,
            tables=results,
        )
        return {
            "ok": False,
            "error": msg,
            "dataset_ref": dataset_ref,
            "window": window_info,
            "tables": results,
        }
    results.append(journeys_stats)
    log_agent_event("materialize_table_built", **journeys_stats)

    total_bytes = sum((r.get("bytes_billed") or 0) for r in results)
    payload = {
        "ok": True,
        "dataset_ref": dataset_ref,
        "window": window_info,
        "cutoffs": cutoffs_info,
        "tables": results,
        "total_bytes_billed": total_bytes,
    }
    log_agent_event("materialize_run_end", **payload)
    return payload
