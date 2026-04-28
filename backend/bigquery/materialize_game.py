"""Build the game_* summary tables used by the mobile-game Deep Scan agent.

Produces five tables in the property's GA4 export dataset:

- ``game_sessions`` -- one row per (``user_pseudo_id``, ``ga_session_id``)
  with **``ga_session_id``** (INT) and **``session_id``** (MD5 hash for stable
  joins). Aggregates mobile-game events: engagement time, ``screen_view`` count,
  short ``event_sequence``, first_open / app_exception signals, platform
  and app version. Built from raw ``events_*``. IAP, ads, and per-screen
  name fields are omitted to keep the schema and scan lean.

- ``game_level_attempts`` -- one row per level attempt keyed by
  (``user_pseudo_id``, ``ga_session_id``, ``level_start.event_timestamp``).
  Includes **``ga_session_id``** for filtering against raw exports. Built by
  stitching each ``level_start`` to its terminal event
  (``level_complete`` / ``level_fail``) and folding the in-attempt events
  (``revive_*``, ``fail_stack_full``, ``fail_time_up``, ``game_paused``,
  ``pause_quit_cancelled``) into booleans / counts. ``user_day_number`` is
  ``DATE_DIFF(session_date, first_open_date, DAY)+1`` when
  ``first_open_date`` is available (from GA ``user_first_touch`` / ``first_open``).

- ``game_user_journeys`` -- one row per ``user_pseudo_id`` with a
  gameplay-focused ``user_group`` label (``new``, ``hooked``,
  ``active_engaged``, ``active_stuck``, ``churned_early``,
  ``churned_progressed``), retention flags, gameplay aggregates
  (farthest level, first-session depth, stuck level, etc), and **``first_open_date``**
  (from ``events_*``). Built from ``game_sessions`` + ``game_level_attempts`` plus
  a per-user scan of ``events_*`` for first-touch -- cheap on top of summaries.

- ``game_levels`` -- one row per ``level_id`` with pre-aggregated
  difficulty / retention metrics (completion rate, fail-reason mix,
  churn-on-level, D1/D7 retention of reachers, top stack-stall items).
  Built from ``game_level_attempts`` + ``game_user_journeys`` -- cheap.
  This is the first table the agent queries for anything per-level.

- ``game_events_test`` -- one row per ``events_*`` row in the materialize window
  with **``attempt_id``** when the event falls inside an attempt span (full
  window scan; for QA / validation of rollups).

Why beta-gameplay, not monetization:
    This module used to produce a two-table set focused on IAP / ad
    revenue. For a game still in beta, payers don't exist in meaningful
    numbers and retention is the only thing that matters. The current
    shape trades monetization aggregates for per-attempt detail pulled
    from the game's custom event instrumentation (``level_start`` /
    ``level_complete`` / ``level_fail`` / ``fail_stack_full`` /
    ``fail_time_up`` / ``revive_*`` / ``game_paused``).

Cost controls mirror ``bigquery_materialize``: window defaults to 90 days
(``GA4_MATERIALIZE_DAYS``), capped to earliest events_* suffix; every job
runs with ``maximum_bytes_billed`` from ``GA4_MATERIALIZE_MAX_BYTES``; and
``use_query_cache`` is off so ``bytes_billed`` reflects real work.

This module reuses window/cutoff/bytes/job helpers from
``bigquery_materialize`` instead of duplicating them, so env-var handling
stays in one place.
"""

from __future__ import annotations

import uuid
from typing import Any

from google.api_core import exceptions as gexc

from backend.bigquery.client import (
    _import_bigquery,
    get_bq_client,
    resolve_dataset_ref,
)
from backend.bigquery.materialize_web import (
    _resolve_cutoffs,
    _resolve_materialize_max_bytes,
    _resolve_window,
    _run_ctas,
    _suffix,
)
from backend.bigquery.runner import (
    enrich_ctas_job_stats,
    estimate_bq_on_demand_usd,
    resolve_bq_on_demand_usd_per_tb,
)
from backend.logs.agent_logging import log_agent_event, log_agent_warning


GAME_SESSIONS_TABLE = "game_sessions"
GAME_LEVEL_ATTEMPTS_TABLE = "game_level_attempts"
GAME_USER_JOURNEYS_TABLE = "game_user_journeys"
GAME_LEVELS_TABLE = "game_levels"
# QA: raw ``events_*`` rows in the materialize window with ``attempt_id`` where
# the event falls inside a ``game_level_attempts`` time span (bytes: full
# events scan + read of attempts).
GAME_EVENTS_TEST_TABLE = "game_events_test"

# Build order: sessions and attempts scan raw ``events_*``; journeys and levels
# read summary tables; ``game_events_test`` joins ``events_*`` to attempts.
GAME_SUMMARY_TABLES = (
    GAME_SESSIONS_TABLE,
    GAME_LEVEL_ATTEMPTS_TABLE,
    GAME_USER_JOURNEYS_TABLE,
    GAME_LEVELS_TABLE,
    GAME_EVENTS_TEST_TABLE,
)


# Thresholds for the beta user_group taxonomy. Kept as module constants so
# they're visible at the top of the file and easy to tune. The values are
# informed observations, not product truths -- revisit after the first real
# materialization lands.
HOOKED_MIN_COMPLETES = 3           # "hooked" requires this many level completes AND d1 retention
STUCK_FAIL_RATIO = 0.7             # "active_stuck" = >= this share of attempts are fails AND no completes
CHURNED_EARLY_MAX_LEVEL = 3        # numeric farthest_level <= this + churned -> "churned_early"


# ---------------------------------------------------------------------------
# SQL builders
# ---------------------------------------------------------------------------

def _build_game_sessions_sql(dataset_ref: str) -> str:
    """CTAS for ``game_sessions``. Scans ``events_*`` once between the window suffixes.

    * ``engagement_time_msec`` is summed with a 2h cap per event.
    * IAP, ads, and per-screen name columns are omitted. ``screen_view_count``
      remains for ``game_user_journeys.total_screen_views`` rollups.
    """
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{GAME_SESSIONS_TABLE}` AS
WITH events AS (
  SELECT
    user_pseudo_id,
    event_name,
    event_timestamp,
    PARSE_DATE('%Y%m%d', event_date) AS event_date_parsed,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'engagement_time_msec') AS engagement_time_msec,
    device.operating_system AS os_name,
    device.operating_system_version AS os_version,
    device.category AS device_category,
    app_info.version AS app_version,
    app_info.id AS app_bundle_id,
    geo.country AS country,
    traffic_source.source AS src,
    traffic_source.medium AS med,
    traffic_source.name AS cmp
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
    ) AS event_rank,
    CASE
      WHEN LOWER(IFNULL(os_name, '')) = 'android' THEN 'Android'
      WHEN LOWER(IFNULL(os_name, '')) IN ('ios', 'iphone os') THEN 'iOS'
      WHEN os_name IS NULL OR os_name = '' THEN NULL
      ELSE os_name
    END AS platform
  FROM events
  WHERE ga_session_id IS NOT NULL
)
SELECT
  TO_HEX(MD5(CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING)))) AS session_id,
  user_pseudo_id,
  ga_session_id,
  MIN(event_date_parsed) AS session_date,
  TIMESTAMP_MICROS(MIN(event_timestamp)) AS session_start_ts,
  MIN(IF(event_rank = 1, platform, NULL)) AS platform,
  MIN(IF(event_rank = 1, os_version, NULL)) AS os_version,
  MIN(IF(event_rank = 1, device_category, NULL)) AS device_category,
  MIN(IF(event_rank = 1, app_version, NULL)) AS app_version,
  MIN(IF(event_rank = 1, app_bundle_id, NULL)) AS app_bundle_id,
  MIN(IF(event_rank = 1, country, NULL)) AS country,
  MIN(IF(event_rank = 1, src, NULL)) AS source,
  MIN(IF(event_rank = 1, med, NULL)) AS medium,
  MIN(IF(event_rank = 1, cmp, NULL)) AS campaign,
  COUNT(*) AS event_count,
  CAST(
    SAFE_DIVIDE(
      SUM(LEAST(IFNULL(engagement_time_msec, 0), 7200000)),
      1000
    ) AS INT64
  ) AS engagement_time_s,
  COUNTIF(event_name = 'screen_view') AS screen_view_count,
  ARRAY_AGG(event_name ORDER BY event_timestamp LIMIT 20) AS event_sequence,
  LOGICAL_OR(event_name = 'first_open') AS had_first_open,
  LOGICAL_OR(event_name = 'app_exception') AS had_app_exception,
  COUNTIF(event_name = 'app_exception') AS app_exception_count
FROM tagged
GROUP BY user_pseudo_id, ga_session_id
"""


def _build_game_level_attempts_sql(dataset_ref: str) -> str:
    """CTAS for ``game_level_attempts``. Scans ``events_*`` a second time.

    One row per (user_pseudo_id, ga_session_id, level_start.event_timestamp).
    Every gameplay event in the same session is attributed to the most recent
    level_start by timestamp (``LAST_VALUE`` window), so in-attempt events
    (revive_*, fail_stack_full, fail_time_up, game_paused,
    pause_quit_cancelled) fold into the same row as their owning
    level_start.

    Booster arrays (e.g. ``[1,0,2,1]``) are stored in event_params as
    strings per the game's spec; we strip brackets/spaces, SPLIT on comma,
    and SAFE_CAST to INT64 per position. Misparsed entries become NULL
    and get treated as 0 by downstream COUNTIF/SUM.

    ``attempt_id`` is a stable MD5 so the agent can join this back to
    ``game_user_journeys`` / ``game_levels`` without recomputing the key.

    Outcome attribution:
      * ``complete`` -- any ``level_complete`` within the attempt window
      * ``fail`` -- any ``level_fail`` but no complete
      * ``abandoned`` -- level_start with neither terminal event seen
        (user killed the app mid-level, session rolled over, etc.)
        These are tracked separately because "nobody finishes attempting"
        is a distinct signal from "people fail".

    Note on the ``shop_purhcase`` param: the spec spells it without the 'c'
    (see sheet row 79/85). We read the spec spelling verbatim so instrumentation
    matches.
    """
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{GAME_LEVEL_ATTEMPTS_TABLE}` AS
WITH user_first_open AS (
  -- GA4 ``user_first_touch_timestamp`` (per event) + ``first_open`` fallback.
  SELECT
    user_pseudo_id,
    COALESCE(
      IF(
        MIN(NULLIF(user_first_touch_timestamp, 0)) IS NOT NULL,
        DATE(TIMESTAMP_MICROS(MIN(NULLIF(user_first_touch_timestamp, 0)))),
        NULL
      ),
      MIN(IF(event_name = 'first_open', PARSE_DATE('%Y%m%d', event_date), NULL))
    ) AS first_open_date
  FROM `{dataset_ref}.events_*`
  WHERE _TABLE_SUFFIX BETWEEN @w_start_suffix AND @w_end_suffix
    AND user_pseudo_id IS NOT NULL
  GROUP BY user_pseudo_id
),
game_events AS (
  SELECT
    user_pseudo_id,
    event_name,
    event_timestamp,
    PARSE_DATE('%Y%m%d', event_date) AS event_date_parsed,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'day_number') AS day_number,
    COALESCE(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'level_id'),
      CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'level_id') AS STRING)
    ) AS level_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'attempt_number') AS attempt_number,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'retry_streak_number') AS retry_streak_number,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'completion_time') AS completion_time,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'fail_time') AS fail_time_val,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'fail_reason') AS fail_reason,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'stars_gained') AS stars_gained,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'items_cleared_perc') AS items_cleared_perc,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'objectives_left_perc') AS objectives_left_perc,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'time_left_perc') AS time_left_perc,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'pre_boosters_chief_level') AS pre_boosters_chief_level,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'boosters_used') AS boosters_used_str,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'pre_boosters_manual_used') AS pre_boosters_manual_used_str,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'end_boosters_used') AS end_boosters_used_str,
    COALESCE(
      (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'shop_purhcase'),
      (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'shop_purchase')
    ) AS shop_purchase_flag,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'from_popup') AS from_popup,
    COALESCE(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'stack_item_1'),
      CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'stack_item_1') AS STRING)
    ) AS stack_item_1,
    COALESCE(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'stack_item_2'),
      CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'stack_item_2') AS STRING)
    ) AS stack_item_2,
    COALESCE(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'stack_item_3'),
      CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'stack_item_3') AS STRING)
    ) AS stack_item_3,
    COALESCE(
      (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'stack_item_last'),
      CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'stack_item_last') AS STRING)
    ) AS stack_item_last,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'ab_test') AS ab_test_param,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'current_level') AS current_level
  FROM `{dataset_ref}.events_*`
  WHERE _TABLE_SUFFIX BETWEEN @w_start_suffix AND @w_end_suffix
    AND user_pseudo_id IS NOT NULL
    AND event_name IN (
      'level_start', 'level_complete', 'level_fail', 'level_retry',
      'revive_clear_bar', 'revive_extra_time',
      'fail_stack_full', 'fail_time_up',
      'game_paused', 'pause_quit_cancelled',
      'custom_session_start'
    )
),
-- Only in-session events (ga_session_id is required to stitch attempts).
-- Also precompute split booster arrays so the aggregation below can SAFE_CAST
-- positional entries without re-regexing.
prepped AS (
  SELECT
    * EXCEPT(boosters_used_str, pre_boosters_manual_used_str, end_boosters_used_str),
    SPLIT(REGEXP_REPLACE(IFNULL(boosters_used_str, ''), r'[\\[\\]\\s]', ''), ',') AS b_arr,
    SPLIT(REGEXP_REPLACE(IFNULL(pre_boosters_manual_used_str, ''), r'[\\[\\]\\s]', ''), ',') AS pbm_arr,
    SPLIT(REGEXP_REPLACE(IFNULL(end_boosters_used_str, ''), r'[\\[\\]\\s]', ''), ',') AS eb_arr
  FROM game_events
  WHERE ga_session_id IS NOT NULL
),
-- Each event gets the timestamp / level_id of its owning level_start
-- (the most recent level_start in the same session at or before this
-- event's timestamp). Events that fire before the first level_start of
-- a session get a NULL attempt and drop out in the GROUP BY below.
with_attempt_key AS (
  SELECT
    *,
    LAST_VALUE(IF(event_name = 'level_start', event_timestamp, NULL) IGNORE NULLS)
      OVER (
        PARTITION BY user_pseudo_id, ga_session_id
        ORDER BY event_timestamp
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      ) AS attempt_start_ts_us,
    LAST_VALUE(IF(event_name = 'level_start', level_id, NULL) IGNORE NULLS)
      OVER (
        PARTITION BY user_pseudo_id, ga_session_id
        ORDER BY event_timestamp
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      ) AS attempt_level_id,
    -- Retry streak from the most recent level_retry at-or-before now. The
    -- retry event fires microseconds before the paired level_start, so the
    -- window function includes it; first attempts (no prior retry) get NULL.
    LAST_VALUE(IF(event_name = 'level_retry', retry_streak_number, NULL) IGNORE NULLS)
      OVER (
        PARTITION BY user_pseudo_id, ga_session_id
        ORDER BY event_timestamp
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      ) AS latest_retry_streak,
    -- ab_test assignment observed on any custom_session_start in this session.
    MAX(IF(event_name = 'custom_session_start', ab_test_param, NULL))
      OVER (PARTITION BY user_pseudo_id, ga_session_id) AS session_ab_test
  FROM prepped
),
attempts_agg AS (
  SELECT
    user_pseudo_id,
    ga_session_id,
    attempt_start_ts_us,
    attempt_level_id AS level_id,
    MIN(event_date_parsed) AS session_date,
    MIN(IF(event_name = 'level_start', current_level, NULL)) AS current_level_at_start,
    MIN(IF(event_name IN ('level_complete', 'level_fail'), attempt_number, NULL)) AS attempt_number,
    MIN(IF(event_name = 'level_start', latest_retry_streak, NULL)) AS retry_streak_number,
    CASE
      WHEN COUNTIF(event_name = 'level_complete') > 0 THEN 'complete'
      WHEN COUNTIF(event_name = 'level_fail') > 0 THEN 'fail'
      ELSE 'abandoned'
    END AS outcome,
    COALESCE(
      MAX(IF(event_name = 'level_complete', completion_time, NULL)),
      MAX(IF(event_name = 'level_fail', fail_time_val, NULL))
    ) AS duration_s,
    MAX(IF(event_name = 'level_fail', fail_reason, NULL)) AS fail_reason,
    MAX(IF(event_name = 'level_complete', stars_gained, NULL)) AS stars_gained,
    -- Take the terminal event's snapshot for progress perc columns; if no
    -- terminal event, fall back to the last fail_* popup or game_paused
    -- event (best-effort snapshot for abandoned attempts).
    COALESCE(
      MAX(IF(event_name IN ('level_complete', 'level_fail'), items_cleared_perc, NULL)),
      MAX(IF(event_name IN ('fail_stack_full', 'fail_time_up', 'game_paused'), items_cleared_perc, NULL))
    ) AS items_cleared_perc,
    COALESCE(
      MAX(IF(event_name IN ('level_complete', 'level_fail'), objectives_left_perc, NULL)),
      MAX(IF(event_name IN ('fail_stack_full', 'fail_time_up', 'game_paused'), objectives_left_perc, NULL))
    ) AS objectives_left_perc,
    COALESCE(
      MAX(IF(event_name IN ('level_complete', 'level_fail'), time_left_perc, NULL)),
      MAX(IF(event_name IN ('fail_stack_full', 'fail_time_up', 'game_paused'), time_left_perc, NULL))
    ) AS time_left_perc,
    MAX(IF(event_name IN ('level_complete', 'level_fail'), pre_boosters_chief_level, NULL)) AS pre_boosters_chief_level,
    -- Booster arrays: MAX across the attempt; terminal events report totals.
    MAX(IF(event_name IN ('level_complete', 'level_fail'),
           SAFE_CAST(b_arr[SAFE_OFFSET(0)] AS INT64), NULL)) AS boosters_vacuum,
    MAX(IF(event_name IN ('level_complete', 'level_fail'),
           SAFE_CAST(b_arr[SAFE_OFFSET(1)] AS INT64), NULL)) AS boosters_spring,
    MAX(IF(event_name IN ('level_complete', 'level_fail'),
           SAFE_CAST(b_arr[SAFE_OFFSET(2)] AS INT64), NULL)) AS boosters_fan,
    MAX(IF(event_name IN ('level_complete', 'level_fail'),
           SAFE_CAST(b_arr[SAFE_OFFSET(3)] AS INT64), NULL)) AS boosters_ice,
    MAX(IF(event_name IN ('level_complete', 'level_fail'),
           SAFE_CAST(pbm_arr[SAFE_OFFSET(0)] AS INT64) > 0, NULL)) AS pre_hammer,
    MAX(IF(event_name IN ('level_complete', 'level_fail'),
           SAFE_CAST(pbm_arr[SAFE_OFFSET(1)] AS INT64) > 0, NULL)) AS pre_sandglass,
    MAX(IF(event_name IN ('level_complete', 'level_fail'),
           SAFE_CAST(eb_arr[SAFE_OFFSET(0)] AS INT64), NULL)) AS end_clear_bar,
    MAX(IF(event_name IN ('level_complete', 'level_fail'),
           SAFE_CAST(eb_arr[SAFE_OFFSET(1)] AS INT64), NULL)) AS end_extra_time,
    COUNTIF(event_name IN ('revive_clear_bar', 'revive_extra_time')) AS revive_count,
    APPROX_TOP_COUNT(
      IF(event_name IN ('revive_clear_bar', 'revive_extra_time'), from_popup, NULL),
      1
    )[SAFE_OFFSET(0)].value AS revive_from_popup_mode,
    LOGICAL_OR(IFNULL(shop_purchase_flag, 0) > 0) AS had_shop_purchase,
    COUNTIF(event_name = 'game_paused') AS pause_count,
    MAX(IF(event_name = 'game_paused', items_cleared_perc, NULL)) AS pause_max_progress_perc,
    COUNTIF(event_name = 'pause_quit_cancelled') AS pause_quit_cancelled_count,
    COUNTIF(event_name = 'fail_stack_full') AS fail_stack_full_popup_count,
    COUNTIF(event_name = 'fail_time_up') AS fail_time_up_popup_count,
    MAX(session_ab_test) AS ab_test,
    -- Stack-fail items: concatenate per-popup arrays across the attempt, then
    -- drop nulls / zero-sentinels. Kept as an ARRAY rather than APPROX_TOP
    -- so downstream per-level rollups can re-aggregate with full fidelity.
    ARRAY_CONCAT_AGG(
      CASE
        WHEN event_name = 'fail_stack_full' THEN
          ARRAY(
            SELECT s
            FROM UNNEST([stack_item_1, stack_item_2, stack_item_3, stack_item_last]) s
            WHERE s IS NOT NULL AND s != '' AND s != '0'
          )
        ELSE []
      END
    ) AS stack_fail_items
  FROM with_attempt_key
  WHERE attempt_start_ts_us IS NOT NULL
    AND attempt_level_id IS NOT NULL
  GROUP BY user_pseudo_id, ga_session_id, attempt_start_ts_us, attempt_level_id
)
SELECT
  TO_HEX(MD5(CONCAT(
    aa.user_pseudo_id, '-',
    CAST(aa.ga_session_id AS STRING), '-',
    CAST(aa.attempt_start_ts_us AS STRING)
  ))) AS attempt_id,
  aa.user_pseudo_id,
  aa.ga_session_id,
  TO_HEX(MD5(CONCAT(aa.user_pseudo_id, '-', CAST(aa.ga_session_id AS STRING)))) AS session_id,
  aa.session_date,
  TIMESTAMP_MICROS(aa.attempt_start_ts_us) AS attempt_start_ts,
  aa.level_id,
  SAFE_CAST(REGEXP_EXTRACT(aa.level_id, r'^\\d+') AS INT64) AS level_id_numeric,
  ufo.first_open_date,
  IF(
    ufo.first_open_date IS NOT NULL,
    DATE_DIFF(aa.session_date, ufo.first_open_date, DAY) + 1,
    NULL
  ) AS user_day_number,
  aa.current_level_at_start,
  aa.attempt_number,
  aa.retry_streak_number,
  aa.outcome,
  aa.duration_s,
  aa.fail_reason,
  aa.stars_gained,
  aa.items_cleared_perc,
  aa.objectives_left_perc,
  aa.time_left_perc,
  aa.pre_boosters_chief_level,
  aa.boosters_vacuum,
  aa.boosters_spring,
  aa.boosters_fan,
  aa.boosters_ice,
  aa.pre_hammer,
  aa.pre_sandglass,
  aa.end_clear_bar,
  aa.end_extra_time,
  aa.revive_count,
  aa.revive_from_popup_mode,
  aa.had_shop_purchase,
  aa.pause_count,
  aa.pause_max_progress_perc,
  aa.pause_quit_cancelled_count,
  aa.fail_stack_full_popup_count,
  aa.fail_time_up_popup_count,
  aa.ab_test,
  aa.stack_fail_items,
  -- "First attempt ever at this level for this user" -- computed after
  -- grouping so the window sees one row per attempt.
  ROW_NUMBER() OVER (
    PARTITION BY aa.user_pseudo_id, aa.level_id
    ORDER BY aa.attempt_start_ts_us
  ) = 1 AS is_first_attempt_ever
FROM attempts_agg AS aa
LEFT JOIN user_first_open AS ufo USING (user_pseudo_id)
"""


def _build_game_user_journeys_sql(
    dataset_ref: str,
    new_cutoff_days: int,
    churn_cutoff_days: int,
    *,
    sessions_table: str = GAME_SESSIONS_TABLE,
    attempts_table: str = GAME_LEVEL_ATTEMPTS_TABLE,
    output_table: str = GAME_USER_JOURNEYS_TABLE,
) -> str:
    """CTAS for ``game_user_journeys``. Aggregates ``game_sessions`` + ``game_level_attempts``.

    ``sessions_table`` / ``attempts_table`` / ``output_table`` default to the
    module constants; set custom names to rebuild journeys from a filtered
    session/attempt slice (e.g. country / app_version Deep Scan).

    Retention scaffolding (D1/D7/D30 flags gated by ``is_eligible_for_dN``)
    carries over from the previous revision; gameplay fields replace the
    payer-focused ones. CTAS is CREATE OR REPLACE so any pre-existing
    legacy payer columns are dropped cleanly on replace.

    ``user_group`` taxonomy (retention-first):
        * ``new``                 -- first_seen within new_cutoff_days of w_end
        * ``hooked``              -- total_completes >= HOOKED_MIN_COMPLETES AND d1_retained
        * ``active_engaged``      -- active + total_completes >= 1 (but not hooked)
        * ``active_stuck``        -- active + zero completes + fails/attempts >= STUCK_FAIL_RATIO
        * ``churned_early``       -- churned + farthest_level_numeric <= CHURNED_EARLY_MAX_LEVEL
                                     (or zero first-session completes)
        * ``churned_progressed``  -- churned + got past the early-quit threshold

    Order matters: the CASE expression cascades top-to-bottom, so earlier
    labels preempt later ones. ``new`` wins first because a brand-new user
    shouldn't also be called ``churned_early`` just for having few levels.
    """
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{output_table}` AS
WITH user_first_open AS (
  SELECT
    user_pseudo_id,
    COALESCE(
      IF(
        MIN(NULLIF(user_first_touch_timestamp, 0)) IS NOT NULL,
        DATE(TIMESTAMP_MICROS(MIN(NULLIF(user_first_touch_timestamp, 0)))),
        NULL
      ),
      MIN(IF(event_name = 'first_open', PARSE_DATE('%Y%m%d', event_date), NULL))
    ) AS first_open_date
  FROM `{dataset_ref}.events_*`
  WHERE _TABLE_SUFFIX BETWEEN @w_start_suffix AND @w_end_suffix
    AND user_pseudo_id IS NOT NULL
  GROUP BY user_pseudo_id
),
session_agg AS (
  SELECT
    user_pseudo_id,
    MIN(session_date) AS first_seen_date,
    MAX(session_date) AS last_seen_date,
    COUNT(*) AS total_sessions,
    SUM(event_count) AS total_events,
    SUM(engagement_time_s) AS total_engagement_s,
    SUM(screen_view_count) AS total_screen_views,
    COUNT(DISTINCT session_date) AS days_active,
    APPROX_TOP_COUNT(platform, 1)[OFFSET(0)].value AS primary_platform,
    APPROX_TOP_COUNT(country, 1)[OFFSET(0)].value AS primary_country,
    APPROX_TOP_COUNT(app_version, 1)[OFFSET(0)].value AS primary_app_version,
    ARRAY_AGG(app_version ORDER BY session_start_ts DESC LIMIT 1)[OFFSET(0)] AS last_app_version,
    ARRAY_AGG(source ORDER BY session_start_ts ASC LIMIT 1)[OFFSET(0)] AS first_touch_source,
    ARRAY_AGG(medium ORDER BY session_start_ts ASC LIMIT 1)[OFFSET(0)] AS first_touch_medium,
    LOGICAL_OR(had_first_open) AS had_first_open,
    LOGICAL_OR(had_app_exception) AS had_app_exception,
    SUM(app_exception_count) AS total_app_exceptions,
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
    COUNTIF(EXTRACT(DAYOFWEEK FROM session_start_ts) NOT IN (1, 7)) AS weekday_sessions,
    -- First session_id and its engagement, picked by earliest session_start_ts.
    -- Two independent ARRAY_AGGs to avoid nesting aggregates.
    ARRAY_AGG(session_id ORDER BY session_start_ts ASC LIMIT 1)[OFFSET(0)] AS first_session_id,
    ARRAY_AGG(engagement_time_s ORDER BY session_start_ts ASC LIMIT 1)[OFFSET(0)] AS first_session_duration_s
  FROM `{dataset_ref}.{sessions_table}`
  GROUP BY user_pseudo_id
),
-- D1/D7/D30 retention is raw here (eligibility gate is applied in the
-- final SELECT). "Retained on day N" means "had at least one session on
-- a date in [first+1, first+N]".
retention AS (
  SELECT
    s.user_pseudo_id,
    LOGICAL_OR(
      s.session_date BETWEEN DATE_ADD(a.first_seen_date, INTERVAL 1 DAY)
                         AND DATE_ADD(a.first_seen_date, INTERVAL 1 DAY)
    ) AS d1_retained_raw,
    LOGICAL_OR(
      s.session_date BETWEEN DATE_ADD(a.first_seen_date, INTERVAL 1 DAY)
                         AND DATE_ADD(a.first_seen_date, INTERVAL 7 DAY)
    ) AS d7_retained_raw,
    LOGICAL_OR(
      s.session_date BETWEEN DATE_ADD(a.first_seen_date, INTERVAL 1 DAY)
                         AND DATE_ADD(a.first_seen_date, INTERVAL 30 DAY)
    ) AS d30_retained_raw
  FROM `{dataset_ref}.{sessions_table}` s
  JOIN session_agg a USING (user_pseudo_id)
  GROUP BY s.user_pseudo_id
),
-- Per-user gameplay aggregates from game_level_attempts. Users who never
-- produced any level_start (e.g. brand-new installs that only sent
-- first_open) will be missing from this CTE -- the final LEFT JOIN
-- coalesces their counts to 0.
attempt_agg AS (
  SELECT
    user_pseudo_id,
    COUNT(*) AS total_attempts,
    COUNTIF(outcome = 'complete') AS total_completes,
    COUNTIF(outcome = 'fail') AS total_fails,
    COUNTIF(outcome = 'abandoned') AS total_abandons,
    SUM(IFNULL(revive_count, 0)) AS total_revives,
    -- Farthest level: the raw level_id string of the attempt with the
    -- highest numeric rank (NULLS LAST so non-numeric ids still sort by
    -- lexical order as the fallback). Keeps the string form that actually
    -- joins back to game_level_attempts.level_id / game_levels.level_id.
    ARRAY_AGG(
      level_id ORDER BY level_id_numeric DESC NULLS LAST, level_id DESC LIMIT 1
    )[OFFSET(0)] AS farthest_level,
    MAX(level_id_numeric) AS farthest_level_numeric,
    ARRAY_AGG(
      IF(outcome = 'complete', level_id, NULL)
      IGNORE NULLS
      ORDER BY level_id_numeric DESC NULLS LAST, level_id DESC
      LIMIT 1
    )[SAFE_OFFSET(0)] AS farthest_completed_level,
    MAX(IF(outcome = 'complete', level_id_numeric, NULL)) AS farthest_completed_numeric,
    -- ab_test assignment: earliest observed per user.
    ARRAY_AGG(
      IF(ab_test IS NOT NULL AND current_level_at_start = 1, ab_test, NULL)
      IGNORE NULLS
      ORDER BY attempt_start_ts ASC
      LIMIT 1
    )[SAFE_OFFSET(0)] AS ab_test_assignment
  FROM `{dataset_ref}.{attempts_table}`
  GROUP BY user_pseudo_id
),
-- Per-user, per-level attempt counts (used to pick a "stuck_level" --
-- the level they failed most without ever completing).
stuck_candidates AS (
  SELECT
    user_pseudo_id,
    level_id,
    COUNTIF(outcome = 'fail') AS fail_count,
    COUNTIF(outcome = 'complete') AS complete_count
  FROM `{dataset_ref}.{attempts_table}`
  GROUP BY user_pseudo_id, level_id
),
stuck_level AS (
  SELECT
    user_pseudo_id,
    ARRAY_AGG(level_id ORDER BY fail_count DESC LIMIT 1)[OFFSET(0)] AS stuck_level,
    MAX(fail_count) AS stuck_level_attempts
  FROM stuck_candidates
  WHERE complete_count = 0 AND fail_count > 0
  GROUP BY user_pseudo_id
),
-- First-session gameplay depth: attempts that occurred in the user's first
-- session (by session_id matched to session_agg.first_session_id).
first_session_attempts AS (
  SELECT
    a.user_pseudo_id,
    COUNT(DISTINCT a.level_id) AS first_session_levels_reached,
    COUNT(DISTINCT IF(a.outcome = 'complete', a.level_id, NULL)) AS first_session_levels_completed
  FROM `{dataset_ref}.{attempts_table}` a
  JOIN session_agg s
    ON a.user_pseudo_id = s.user_pseudo_id
   AND a.session_id = s.first_session_id
  GROUP BY a.user_pseudo_id
)
SELECT
  s.user_pseudo_id,
  ufo.first_open_date,
  s.first_seen_date,
  s.last_seen_date,
  DATE_DIFF(s.last_seen_date, s.first_seen_date, DAY) AS days_active_span,
  s.total_sessions,
  s.days_active,
  s.total_events,
  s.total_engagement_s,
  s.total_screen_views,
  s.primary_platform,
  s.primary_country,
  s.primary_app_version,
  s.last_app_version,
  s.first_touch_source,
  s.first_touch_medium,
  s.had_first_open,
  s.had_app_exception,
  s.total_app_exceptions,
  s.time_of_day_mode,
  CASE
    WHEN s.weekend_sessions = 0 THEN 'weekday'
    WHEN s.weekday_sessions = 0 THEN 'weekend'
    ELSE 'mixed'
  END AS weekday_weekend,
  CASE WHEN DATE_ADD(s.first_seen_date, INTERVAL 1 DAY) <= @w_end
       THEN IFNULL(r.d1_retained_raw, FALSE) ELSE NULL END AS d1_retained,
  CASE WHEN DATE_ADD(s.first_seen_date, INTERVAL 7 DAY) <= @w_end
       THEN IFNULL(r.d7_retained_raw, FALSE) ELSE NULL END AS d7_retained,
  CASE WHEN DATE_ADD(s.first_seen_date, INTERVAL 30 DAY) <= @w_end
       THEN IFNULL(r.d30_retained_raw, FALSE) ELSE NULL END AS d30_retained,
  DATE_ADD(s.first_seen_date, INTERVAL 1 DAY) <= @w_end AS is_eligible_for_d1,
  DATE_ADD(s.first_seen_date, INTERVAL 7 DAY) <= @w_end AS is_eligible_for_d7,
  DATE_ADD(s.first_seen_date, INTERVAL 30 DAY) <= @w_end AS is_eligible_for_d30,
  s.first_seen_date <= DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY) AS is_eligible_for_churn,
  -- is_churned: eligible and last_seen older than the cutoff.
  (s.first_seen_date <= DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY)
   AND s.last_seen_date <= DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY)) AS is_churned,
  -- Gameplay aggregates.
  IFNULL(att.total_attempts, 0) AS total_attempts,
  IFNULL(att.total_completes, 0) AS total_completes,
  IFNULL(att.total_fails, 0) AS total_fails,
  IFNULL(att.total_abandons, 0) AS total_abandons,
  IFNULL(att.total_revives, 0) AS total_revives,
  att.farthest_level,
  att.farthest_level_numeric,
  att.farthest_completed_level,
  att.farthest_completed_numeric,
  IFNULL(fsa.first_session_levels_reached, 0) AS first_session_levels_reached,
  IFNULL(fsa.first_session_levels_completed, 0) AS first_session_levels_completed,
  s.first_session_duration_s,
  sl.stuck_level,
  sl.stuck_level_attempts,
  att.ab_test_assignment,
  s.first_session_id,
  -- user_group: see header docstring. Evaluation order matters.
  CASE
    WHEN s.first_seen_date > DATE_SUB(@w_end, INTERVAL {new_cutoff_days} DAY) THEN 'new'
    WHEN IFNULL(att.total_completes, 0) >= {HOOKED_MIN_COMPLETES}
         AND DATE_ADD(s.first_seen_date, INTERVAL 1 DAY) <= @w_end
         AND IFNULL(r.d1_retained_raw, FALSE) = TRUE
      THEN 'hooked'
    WHEN s.last_seen_date > DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY)
         AND IFNULL(att.total_completes, 0) >= 1
      THEN 'active_engaged'
    WHEN s.last_seen_date > DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY)
         AND IFNULL(att.total_completes, 0) = 0
         AND IFNULL(att.total_attempts, 0) > 0
         AND SAFE_DIVIDE(att.total_fails, att.total_attempts) >= {STUCK_FAIL_RATIO}
      THEN 'active_stuck'
    WHEN s.last_seen_date <= DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY)
         AND (IFNULL(att.farthest_level_numeric, 0) <= {CHURNED_EARLY_MAX_LEVEL}
              OR IFNULL(fsa.first_session_levels_completed, 0) = 0)
      THEN 'churned_early'
    WHEN s.last_seen_date <= DATE_SUB(@w_end, INTERVAL {churn_cutoff_days} DAY)
      THEN 'churned_progressed'
    ELSE 'other'
  END AS user_group
FROM session_agg s
LEFT JOIN user_first_open ufo USING (user_pseudo_id)
LEFT JOIN retention r USING (user_pseudo_id)
LEFT JOIN attempt_agg att USING (user_pseudo_id)
LEFT JOIN stuck_level sl USING (user_pseudo_id)
LEFT JOIN first_session_attempts fsa USING (user_pseudo_id)
"""


def _build_game_levels_sql(
    dataset_ref: str,
    *,
    attempts_table: str = GAME_LEVEL_ATTEMPTS_TABLE,
    journeys_table: str = GAME_USER_JOURNEYS_TABLE,
    output_table: str = GAME_LEVELS_TABLE,
) -> str:
    """CTAS for ``game_levels``. Per-level difficulty + retention rollup.

    Reads ``game_level_attempts`` (for difficulty) and ``game_user_journeys``
    (for retention flags on reachers). Cheap -- MB scale.

    Override table names to rebuild from filtered attempts + filtered journeys
    (same SQL as the main job, different inputs).

    ``churn_on_level_rate`` is the share of eligible users whose
    ``farthest_level == this level`` AND ``is_churned`` -- i.e. this level
    was their personal ceiling. The gate on ``is_eligible_for_churn``
    prevents recent installs (who simply haven't had time to churn yet)
    from polluting the rate.

    D1 / D7 retention is computed over the set of users who REACHED this
    level (had any attempt at it), eligible for the respective horizon.
    """
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{output_table}` AS
WITH level_users AS (
  SELECT
    a.level_id,
    a.level_id_numeric,
    a.user_pseudo_id,
    COUNTIF(a.outcome = 'complete') AS user_completes,
    COUNTIF(a.outcome = 'fail') AS user_fails,
    COUNTIF(a.outcome = 'abandoned') AS user_abandons,
    COUNT(*) AS user_attempts
  FROM `{dataset_ref}.{attempts_table}` a
  GROUP BY a.level_id, a.level_id_numeric, a.user_pseudo_id
),
-- Per-level aggregates computed once at attempt grain (difficulty metrics).
level_agg AS (
  SELECT
    a.level_id,
    ANY_VALUE(a.level_id_numeric) AS level_id_numeric,
    COUNT(*) AS total_attempts,
    COUNT(DISTINCT a.user_pseudo_id) AS unique_starters,
    COUNTIF(a.outcome = 'complete') AS total_completes,
    COUNTIF(a.outcome = 'fail') AS total_fails,
    COUNTIF(a.outcome = 'abandoned') AS total_abandons,
    COUNTIF(a.outcome = 'complete' AND a.is_first_attempt_ever) AS first_try_wins,
    SAFE_DIVIDE(
      APPROX_QUANTILES(IF(a.outcome = 'complete', a.duration_s, NULL), 2)[SAFE_OFFSET(1)],
      1
    ) AS median_duration_complete_s,
    SAFE_DIVIDE(
      APPROX_QUANTILES(IF(a.outcome = 'fail', a.duration_s, NULL), 2)[SAFE_OFFSET(1)],
      1
    ) AS median_duration_fail_s,
    COUNTIF(a.outcome = 'fail' AND a.fail_reason = 'stack_full') AS fail_stack_full_count,
    COUNTIF(a.outcome = 'fail' AND a.fail_reason = 'time_up') AS fail_time_up_count,
    COUNTIF(a.outcome = 'fail' AND a.fail_reason = 'pause_quit') AS fail_pause_quit_count,
    COUNTIF(
      IFNULL(a.boosters_vacuum, 0) + IFNULL(a.boosters_spring, 0)
      + IFNULL(a.boosters_fan, 0) + IFNULL(a.boosters_ice, 0) > 0
    ) AS attempts_with_ingame_booster,
    COUNTIF(IFNULL(a.revive_count, 0) > 0) AS attempts_with_revive,
    AVG(IF(a.outcome = 'fail', a.items_cleared_perc, NULL)) AS avg_items_cleared_perc_on_fail,
    AVG(IF(a.outcome = 'fail', a.objectives_left_perc, NULL)) AS avg_objectives_left_perc_on_fail,
    AVG(IF(a.outcome = 'fail', a.time_left_perc, NULL)) AS avg_time_left_perc_on_fail,
    AVG(IF(a.outcome = 'complete', a.stars_gained, NULL)) AS avg_stars_on_complete
  FROM `{dataset_ref}.{attempts_table}` a
  GROUP BY a.level_id
),
-- Stack-fail items flattened to (level_id, item) per appearance so we can
-- rank by frequency via GROUP BY + ARRAY_AGG (APPROX_TOP_COUNT doesn't take
-- an ARRAY input; this avoids that limitation).
stack_items_flat AS (
  SELECT a.level_id, item
  FROM `{dataset_ref}.{attempts_table}` a,
    UNNEST(a.stack_fail_items) AS item
  WHERE a.fail_reason = 'stack_full'
    AND item IS NOT NULL
    AND item != ''
    AND item != '0'
),
stack_item_counts AS (
  SELECT level_id, item, COUNT(*) AS cnt
  FROM stack_items_flat
  GROUP BY level_id, item
),
top_stall AS (
  SELECT
    level_id,
    ARRAY_AGG(item ORDER BY cnt DESC, item LIMIT 5) AS top_stack_stall_items
  FROM stack_item_counts
  GROUP BY level_id
),
-- Per-level user-rollup (attempts-to-beat, completers count).
level_user_agg AS (
  SELECT
    level_id,
    COUNT(DISTINCT IF(user_completes > 0, user_pseudo_id, NULL)) AS unique_completers,
    APPROX_QUANTILES(
      IF(user_completes > 0, user_attempts, NULL), 10
    )[SAFE_OFFSET(5)] AS median_attempts_to_beat,
    APPROX_QUANTILES(
      IF(user_completes > 0, user_attempts, NULL), 10
    )[SAFE_OFFSET(9)] AS p90_attempts_to_beat
  FROM level_users
  GROUP BY level_id
),
-- Churn-on-level + D1/D7 retention of reachers. Joined via user_pseudo_id
-- to the journeys table so only CHURN-eligible or D{1,7}-eligible users
-- contribute to their respective denominators.
level_retention AS (
  SELECT
    lu.level_id,
    COUNTIF(j.is_eligible_for_churn) AS churn_eligible_reachers,
    COUNTIF(
      j.is_eligible_for_churn AND j.is_churned AND j.farthest_level = lu.level_id
    ) AS churned_here_count,
    COUNTIF(j.is_eligible_for_d1) AS d1_eligible_reachers,
    COUNTIF(j.is_eligible_for_d1 AND j.d1_retained = TRUE) AS d1_retained_reachers,
    COUNTIF(j.is_eligible_for_d7) AS d7_eligible_reachers,
    COUNTIF(j.is_eligible_for_d7 AND j.d7_retained = TRUE) AS d7_retained_reachers
  FROM level_users lu
  JOIN `{dataset_ref}.{journeys_table}` j USING (user_pseudo_id)
  GROUP BY lu.level_id
)
SELECT
  la.level_id,
  la.level_id_numeric,
  la.unique_starters,
  lua.unique_completers,
  SAFE_DIVIDE(lua.unique_completers, la.unique_starters) AS completion_rate,
  SAFE_DIVIDE(la.first_try_wins, la.unique_starters) AS first_try_win_rate,
  lua.median_attempts_to_beat,
  lua.p90_attempts_to_beat,
  la.total_attempts,
  la.total_completes,
  la.total_fails,
  la.total_abandons,
  la.median_duration_complete_s,
  la.median_duration_fail_s,
  SAFE_DIVIDE(la.fail_stack_full_count, la.total_fails) AS fail_rate_stack_full,
  SAFE_DIVIDE(la.fail_time_up_count, la.total_fails) AS fail_rate_time_up,
  SAFE_DIVIDE(la.fail_pause_quit_count, la.total_fails) AS fail_rate_pause_quit,
  SAFE_DIVIDE(la.total_abandons, la.total_attempts) AS abandon_rate,
  SAFE_DIVIDE(la.attempts_with_ingame_booster, la.total_attempts) AS booster_attempt_rate,
  SAFE_DIVIDE(la.attempts_with_revive, la.total_attempts) AS revive_attempt_rate,
  la.avg_items_cleared_perc_on_fail,
  la.avg_objectives_left_perc_on_fail,
  la.avg_time_left_perc_on_fail,
  la.avg_stars_on_complete,
  lr.churn_eligible_reachers AS n_users_reached_churn_eligible,
  lr.churned_here_count AS n_users_who_churned_here,
  SAFE_DIVIDE(lr.churned_here_count, lr.churn_eligible_reachers) AS churn_on_level_rate,
  lr.d1_eligible_reachers,
  SAFE_DIVIDE(lr.d1_retained_reachers, lr.d1_eligible_reachers) AS d1_retention_of_reachers,
  lr.d7_eligible_reachers,
  SAFE_DIVIDE(lr.d7_retained_reachers, lr.d7_eligible_reachers) AS d7_retention_of_reachers,
  IFNULL(ts.top_stack_stall_items, []) AS top_stack_stall_items
FROM level_agg la
LEFT JOIN level_user_agg lua USING (level_id)
LEFT JOIN level_retention lr USING (level_id)
LEFT JOIN top_stall ts USING (level_id)
"""


def _new_filtered_scan_suffix() -> str:
    """Return a short unique fragment for temp game_* table names (BQ-safe)."""
    return f"f_{uuid.uuid4().hex[:10]}"


def _build_filtered_game_sessions_sql(dataset_ref: str, out_table: str) -> str:
    """CTAS from ``game_sessions`` with session-level country / app_version filters.

    ``@countries`` / ``@app_versions`` are STRING array parameters. An empty
    array means "no filter" for that dimension. When both are empty, all
    rows are included (``materialize`` should skip calling this in that case).
    """
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{out_table}` AS
SELECT g.*
FROM `{dataset_ref}.{GAME_SESSIONS_TABLE}` g
WHERE (ARRAY_LENGTH(@countries) = 0 OR g.country IN UNNEST(@countries))
  AND (ARRAY_LENGTH(@app_versions) = 0 OR g.app_version IN UNNEST(@app_versions))
"""


def _build_filtered_game_level_attempts_sql(
    dataset_ref: str, sessions_table: str, out_table: str
) -> str:
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{out_table}` AS
SELECT a.*
FROM `{dataset_ref}.{GAME_LEVEL_ATTEMPTS_TABLE}` a
INNER JOIN `{dataset_ref}.{sessions_table}` s ON a.session_id = s.session_id
"""


def materialize_game_filtered_for_deep_scan(
    property_id: str,
    filter_countries: list[str] | None,
    filter_app_versions: list[str] | None,
    days: int | None = None,
) -> dict[str, Any]:
    """Build temp ``game_*`` tables for a country/app_version filtered Deep Scan.

    Reuses the same user-journey and level aggregation SQL as the main
    materialize job, but with inputs restricted to sessions matching the
    filter (AND of non-empty country / version lists) and attempts whose
    ``session_id`` is in that session set.

    Returns ``{ok, error?, dataset_ref, suffix, physical_tables, fqn_by_logical, ...}``
    for the API layer; callers must :func:`drop_game_filtered_scan_tables` in a
    ``finally`` block when ``ok`` is true.
    """
    bq = _import_bigquery()
    countries = [c for c in (filter_countries or []) if c]
    app_versions = [v for v in (filter_app_versions or []) if v]
    if not countries and not app_versions:
        return {
            "ok": False,
            "error": "At least one country or app_version filter is required.",
        }

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
    window_info: dict[str, Any] = {
        "start": str(w_start),
        "end": str(w_end),
        "days": window_days,
    }
    new_cutoff_days, churn_cutoff_days = _resolve_cutoffs(window_days)
    cutoffs_info = {
        "new_cutoff_days": new_cutoff_days,
        "churn_cutoff_days": churn_cutoff_days,
    }

    tag = _new_filtered_scan_suffix()
    sessions_f = f"{GAME_SESSIONS_TABLE}_{tag}"
    attempts_f = f"{GAME_LEVEL_ATTEMPTS_TABLE}_{tag}"
    journeys_f = f"{GAME_USER_JOURNEYS_TABLE}_{tag}"
    levels_f = f"{GAME_LEVELS_TABLE}_{tag}"

    physical = {
        "game_sessions": sessions_f,
        "game_level_attempts": attempts_f,
        "game_user_journeys": journeys_f,
        "game_levels": levels_f,
    }

    def _fqs(table: str) -> str:
        return f"`{dataset_ref}.{table}`"

    fqn_by_logical = {k: _fqs(v) for k, v in physical.items()}

    created: list[str] = []

    def _run_drop_created() -> None:
        for t in reversed(created):
            try:
                client.delete_table(f"{dataset_ref}.{t}", not_found_ok=True)
            except Exception:  # noqa: BLE001
                pass

    try:
        sess_cfg = bq.QueryJobConfig(
            maximum_bytes_billed=max_bytes,
            use_query_cache=False,
            query_parameters=[
                bq.ArrayQueryParameter("countries", "STRING", countries),
                bq.ArrayQueryParameter("app_versions", "STRING", app_versions),
            ],
        )
        st = _run_ctas(
            client,
            _build_filtered_game_sessions_sql(dataset_ref, sessions_f),
            sess_cfg,
            dataset_ref,
            sessions_f,
        )
        enrich_ctas_job_stats(st, max_bytes)
        created.append(sessions_f)

        att_cfg = bq.QueryJobConfig(
            maximum_bytes_billed=max_bytes,
            use_query_cache=False,
        )
        st2 = _run_ctas(
            client,
            _build_filtered_game_level_attempts_sql(
                dataset_ref, sessions_f, attempts_f
            ),
            att_cfg,
            dataset_ref,
            attempts_f,
        )
        enrich_ctas_job_stats(st2, max_bytes)
        created.append(attempts_f)

        j_cfg = bq.QueryJobConfig(
            maximum_bytes_billed=max_bytes,
            use_query_cache=False,
            query_parameters=[
                bq.ScalarQueryParameter("w_start_suffix", "STRING", _suffix(w_start)),
                bq.ScalarQueryParameter("w_end_suffix", "STRING", _suffix(w_end)),
                bq.ScalarQueryParameter("w_end", "DATE", w_end),
            ],
        )
        st3 = _run_ctas(
            client,
            _build_game_user_journeys_sql(
                dataset_ref,
                new_cutoff_days,
                churn_cutoff_days,
                sessions_table=sessions_f,
                attempts_table=attempts_f,
                output_table=journeys_f,
            ),
            j_cfg,
            dataset_ref,
            journeys_f,
        )
        enrich_ctas_job_stats(st3, max_bytes)
        created.append(journeys_f)

        lv_cfg = bq.QueryJobConfig(
            maximum_bytes_billed=max_bytes,
            use_query_cache=False,
        )
        st4 = _run_ctas(
            client,
            _build_game_levels_sql(
                dataset_ref,
                attempts_table=attempts_f,
                journeys_table=journeys_f,
                output_table=levels_f,
            ),
            lv_cfg,
            dataset_ref,
            levels_f,
        )
        enrich_ctas_job_stats(st4, max_bytes)
        created.append(levels_f)
    except Exception as exc:  # noqa: BLE001
        _run_drop_created()
        return {
            "ok": False,
            "error": str(exc),
            "dataset_ref": dataset_ref,
            "window": window_info,
        }

    return {
        "ok": True,
        "dataset_ref": dataset_ref,
        "window": window_info,
        "cutoffs": cutoffs_info,
        "suffix": tag,
        "physical_tables": physical,
        "fqn_by_logical": fqn_by_logical,
        "filter": {
            "countries": countries,
            "app_versions": app_versions,
        },
        "filter_rule": (
            "Per session, include the row if (no country list OR country IN list) "
            "AND (no app_version list OR app_version IN list). Journeys and "
            "levels are recomputed from this subset only."
        ),
        "tables_built": [sessions_f, attempts_f, journeys_f, levels_f],
    }


def drop_game_filtered_scan_tables(property_id: str, table_names: list[str]) -> None:
    """Best-effort DROP for temp filtered-scan tables. Ignores missing tables."""
    if not table_names:
        return
    try:
        dataset_ref = resolve_dataset_ref(property_id)
    except ValueError:
        return
    try:
        client = get_bq_client()
    except ValueError:
        return
    for t in table_names:
        try:
            client.delete_table(f"{dataset_ref}.{t}", not_found_ok=True)
        except Exception:  # noqa: BLE001
            pass


def _build_game_events_test_sql(dataset_ref: str) -> str:
    """CTAS for ``game_events_test``. One row per raw ``events_*`` row in the window.

    Device/geo/app/traffic fields mirror what ``_build_game_sessions_sql`` uses,
    but taken **per event** from the export row (not session-rolled-up).

    ``attempt_id`` is filled only by matching the event into an attempt time span
    read from the already-built ``game_level_attempts`` helper CTE (same as
    before). No other joins to summary tables.
    """
    return f"""
CREATE OR REPLACE TABLE `{dataset_ref}.{GAME_EVENTS_TEST_TABLE}` AS
WITH att AS (
  SELECT
    user_pseudo_id,
    ga_session_id,
    attempt_start_ts,
    UNIX_MICROS(attempt_start_ts) AS attempt_start_us,
    attempt_id,
    LEAD(UNIX_MICROS(attempt_start_ts)) OVER (
      PARTITION BY user_pseudo_id, ga_session_id
      ORDER BY attempt_start_ts
    ) AS next_attempt_start_us
  FROM `{dataset_ref}.{GAME_LEVEL_ATTEMPTS_TABLE}`
),
event_rows AS (
  SELECT
    e.user_pseudo_id,
    e.event_date,
    e.event_timestamp,
    e.event_name,
    e.event_params,
    e.user_first_touch_timestamp,
    (SELECT value.int_value FROM UNNEST(e.event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    e.geo.country AS country,
    e.app_info.version AS app_version,
    e.app_info.id AS app_bundle_id,
    e.device.operating_system AS os_name,
    e.device.operating_system_version AS os_version,
    e.device.category AS device_category,
    e.traffic_source.source AS source,
    e.traffic_source.medium AS medium,
    e.traffic_source.name AS campaign,
    CASE
      WHEN LOWER(IFNULL(e.device.operating_system, '')) = 'android' THEN 'Android'
      WHEN LOWER(IFNULL(e.device.operating_system, '')) IN ('ios', 'iphone os') THEN 'iOS'
      WHEN e.device.operating_system IS NULL OR e.device.operating_system = '' THEN NULL
      ELSE e.device.operating_system
    END AS platform
  FROM `{dataset_ref}.events_*` AS e
  WHERE e._TABLE_SUFFIX BETWEEN @w_start_suffix AND @w_end_suffix
    AND e.user_pseudo_id IS NOT NULL
)
SELECT
  e.user_pseudo_id,
  e.event_date,
  e.event_timestamp,
  TIMESTAMP_MICROS(e.event_timestamp) AS event_ts,
  e.event_name,
  e.ga_session_id,
  e.event_params,
  e.user_first_touch_timestamp,
  a.attempt_id,
  e.platform,
  e.os_version,
  e.device_category,
  e.app_version,
  e.app_bundle_id,
  e.country,
  e.source,
  e.medium,
  e.campaign
FROM event_rows AS e
LEFT JOIN att AS a
  ON e.user_pseudo_id = a.user_pseudo_id
 AND e.ga_session_id = a.ga_session_id
 AND e.event_timestamp >= a.attempt_start_us
 AND (a.next_attempt_start_us IS NULL OR e.event_timestamp < a.next_attempt_start_us)
"""


# ---------------------------------------------------------------------------
# Materialize entrypoint
# ---------------------------------------------------------------------------

def _handle_build_failure(
    table_name: str,
    exc: Exception,
    dataset_ref: str,
    window_info: dict[str, Any],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the standard failure payload and log a warning.

    Consolidates the repetitive try/except shape we use per CTAS. Translates
    Forbidden / BadRequest into operator-facing messages; anything else
    surfaces the raw exception so the caller can decide what to do.
    """
    if isinstance(exc, gexc.Forbidden):
        msg = (
            f"Permission denied building {table_name}. The platform service "
            f"account needs bigquery.dataEditor on {dataset_ref}. "
            f"({getattr(exc, 'message', str(exc))})"
        )
    elif isinstance(exc, gexc.BadRequest):
        msg = (
            f"BigQuery rejected {table_name} build: "
            f"{getattr(exc, 'message', str(exc))}"
        )
    else:
        msg = f"Failed building {table_name}: {exc}"
    log_agent_warning(
        "materialize_game_run_end",
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


def materialize_all_game(
    property_id: str,
    days: int | None = None,
) -> dict[str, Any]:
    """Build the mobile-game summary tables and QA join table for one property.

    Build order (cost-weighted, early failures short-circuit):
        1. ``game_sessions``         -- scans raw events_*
        2. ``game_level_attempts``   -- scans raw events_* again, filtered to gameplay events
        3. ``game_user_journeys``    -- reads game_sessions + game_level_attempts; scans
                                      events_* for per-user first_open_date
        4. ``game_levels``           -- reads game_level_attempts + game_user_journeys
        5. ``game_events_test``     -- full events_* window join to attempts (QA / debugging)

    The second raw-events scan is intentional: the first pulls broad session
    columns, the second pulls gameplay-specific event_params with a WHERE
    filter on event_name that cuts bytes scanned substantially. Keeping them
    separate keeps each SQL block readable and each CTAS independently
    re-runnable.

    Return shape mirrors ``bigquery_materialize.materialize_all`` so the
    existing ``POST /api/bigquery/materialize`` response schema is reused.
    If ``game_level_attempts`` comes back with zero rows (custom events not
    yet exporting), we return ``ok: True`` with a ``warning`` flag rather
    than failing -- the Deep Scan agent will detect the empty table and
    surface a clean "custom gameplay events not present yet" message.
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
        "materialize_game_run_start",
        property_id=property_id,
        dataset_ref=dataset_ref,
        window=window_info,
        cutoffs=cutoffs_info,
        max_bytes_billed=max_bytes,
    )

    results: list[dict[str, Any]] = []

    # 1) game_sessions -- raw events_* scan #1
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
            _build_game_sessions_sql(dataset_ref),
            sessions_config,
            dataset_ref,
            GAME_SESSIONS_TABLE,
        )
    except Exception as exc:  # noqa: BLE001
        return _handle_build_failure(
            GAME_SESSIONS_TABLE, exc, dataset_ref, window_info, results
        )
    enrich_ctas_job_stats(sessions_stats, max_bytes)
    results.append(sessions_stats)
    log_agent_event("materialize_game_table_built", **sessions_stats)

    # 2) game_level_attempts -- raw events_* scan #2 (gameplay events only)
    attempts_config = bq.QueryJobConfig(
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
        query_parameters=[
            bq.ScalarQueryParameter("w_start_suffix", "STRING", _suffix(w_start)),
            bq.ScalarQueryParameter("w_end_suffix", "STRING", _suffix(w_end)),
        ],
    )
    try:
        attempts_stats = _run_ctas(
            client,
            _build_game_level_attempts_sql(dataset_ref),
            attempts_config,
            dataset_ref,
            GAME_LEVEL_ATTEMPTS_TABLE,
        )
    except Exception as exc:  # noqa: BLE001
        return _handle_build_failure(
            GAME_LEVEL_ATTEMPTS_TABLE, exc, dataset_ref, window_info, results
        )
    enrich_ctas_job_stats(attempts_stats, max_bytes)
    results.append(attempts_stats)
    log_agent_event("materialize_game_table_built", **attempts_stats)

    # 3) game_user_journeys -- reads sessions + attempts; scans events_* for
    #    user_first_open (same window as materialize)
    journeys_config = bq.QueryJobConfig(
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
        query_parameters=[
            bq.ScalarQueryParameter("w_start_suffix", "STRING", _suffix(w_start)),
            bq.ScalarQueryParameter("w_end_suffix", "STRING", _suffix(w_end)),
            bq.ScalarQueryParameter("w_end", "DATE", w_end),
        ],
    )
    try:
        journeys_stats = _run_ctas(
            client,
            _build_game_user_journeys_sql(
                dataset_ref,
                new_cutoff_days=new_cutoff_days,
                churn_cutoff_days=churn_cutoff_days,
            ),
            journeys_config,
            dataset_ref,
            GAME_USER_JOURNEYS_TABLE,
        )
    except Exception as exc:  # noqa: BLE001
        return _handle_build_failure(
            GAME_USER_JOURNEYS_TABLE, exc, dataset_ref, window_info, results
        )
    enrich_ctas_job_stats(journeys_stats, max_bytes)
    results.append(journeys_stats)
    log_agent_event("materialize_game_table_built", **journeys_stats)

    # 4) game_levels -- reads attempts + journeys
    levels_config = bq.QueryJobConfig(
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
    )
    try:
        levels_stats = _run_ctas(
            client,
            _build_game_levels_sql(dataset_ref),
            levels_config,
            dataset_ref,
            GAME_LEVELS_TABLE,
        )
    except Exception as exc:  # noqa: BLE001
        return _handle_build_failure(
            GAME_LEVELS_TABLE, exc, dataset_ref, window_info, results
        )
    enrich_ctas_job_stats(levels_stats, max_bytes)
    results.append(levels_stats)
    log_agent_event("materialize_game_table_built", **levels_stats)

    # 5) game_events_test -- full events_* scan + read game_level_attempts
    test_config = bq.QueryJobConfig(
        maximum_bytes_billed=max_bytes,
        use_query_cache=False,
        query_parameters=[
            bq.ScalarQueryParameter("w_start_suffix", "STRING", _suffix(w_start)),
            bq.ScalarQueryParameter("w_end_suffix", "STRING", _suffix(w_end)),
        ],
    )
    try:
        test_stats = _run_ctas(
            client,
            _build_game_events_test_sql(dataset_ref),
            test_config,
            dataset_ref,
            GAME_EVENTS_TEST_TABLE,
        )
    except Exception as exc:  # noqa: BLE001
        return _handle_build_failure(
            GAME_EVENTS_TEST_TABLE, exc, dataset_ref, window_info, results
        )
    enrich_ctas_job_stats(test_stats, max_bytes)
    results.append(test_stats)
    log_agent_event("materialize_game_table_built", **test_stats)

    total_bytes = sum((r.get("bytes_billed") or 0) for r in results)
    total_est_usd = estimate_bq_on_demand_usd(total_bytes)

    # Soft warning: if game_level_attempts has zero rows, the game's custom
    # events haven't started exporting yet. Callers can still show the
    # summary; the Deep Scan agent detects the empty table and explains.
    attempts_rows = next(
        (r.get("rows") for r in results if r.get("table") == GAME_LEVEL_ATTEMPTS_TABLE),
        None,
    )
    warning = None
    if attempts_rows is not None and attempts_rows == 0:
        warning = (
            "game_level_attempts is empty -- no level_start / level_complete / "
            "level_fail events found in the window. The GA4 export may not yet "
            "contain the game's custom gameplay events."
        )

    payload = {
        "ok": True,
        "dataset_ref": dataset_ref,
        "window": window_info,
        "cutoffs": cutoffs_info,
        "tables": results,
        "total_bytes_billed": total_bytes,
        "cost_estimate": {
            "total_est_cost_usd": round(total_est_usd, 6) if total_est_usd is not None else None,
            "total_bytes_billed": total_bytes,
            "usd_per_tb_assumed": resolve_bq_on_demand_usd_per_tb(),
            "max_bytes_billed_per_job": max_bytes,
            "note": (
                "est_cost_usd is approximate on-demand $/TB (env "
                "GA4_BQ_ON_DEMAND_USD_PER_TB; default 6.25). Per-table "
                "est_cost_usd uses each job's bytes_billed; sum matches "
                "total when all materialize jobs succeed. Actual GCP invoices may "
                "differ (committed use, region, slots, etc.)."
            ),
        },
    }
    if warning:
        payload["warning"] = warning
    log_agent_event("materialize_game_run_end", **payload)
    return payload
