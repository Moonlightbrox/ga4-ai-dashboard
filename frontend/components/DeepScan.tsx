"use client";

/**
 * DeepScan -- the Deep Scan button entry point for both agents.
 *
 * Two-phase UX driven by a materialize-status probe:
 *   1. Phase 1 (materialize): if any summary table is missing, hit the
 *      property's materialize endpoint to (re)build them. This is the
 *      expensive ``events_*`` scan.
 *   2. Phase 2 (analyze): hit the agent's run endpoint with
 *      ``mode='deep_scan'`` so the orchestrator prompt drives the
 *      narrative. Result is rendered with the shared :func:`AnswerRenderer`
 *      so the formatting matches the chat path exactly.
 *
 * The component is scope-agnostic via ``config``. Two presets ship below:
 *   * :data:`SITE_DEEP_SCAN_CONFIG` -- web analyst, ``site_*`` tables.
 *   * :data:`GAME_DEEP_SCAN_CONFIG` -- game analyst, ``game_*`` tables,
 *     optional country / app_version slice.
 */

import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import {
  getGameSessionFilterOptions,
  getMaterializeGameStatus,
  getMaterializeWebStatus,
  postMaterializeGame,
  postMaterializeWeb,
  runGameAgent,
  runWebAgent,
  type AgentRunResponse,
  type MaterializeResponse,
  type MaterializeStatusResponse,
} from "../lib/api";
import { AnswerRenderer } from "./AnswerRenderer";


/** Optional session-level slice for the game Deep Scan. */
export type GameDeepScanRunOpts = {
  filter_countries?: string[];
  filter_app_versions?: string[];
};

export type DeepScanConfig = {
  title: string;
  description: ReactNode;
  storageKey: string;
  fetchStatus: () => Promise<MaterializeStatusResponse>;
  runMaterialize: () => Promise<MaterializeResponse>;
  runScan: (opts?: GameDeepScanRunOpts) => Promise<AgentRunResponse>;
  /** When set, the UI loads distinct countries / app_versions before step 2. */
  gameSessionFilters?: {
    loadOptions: () => Promise<{
      countries: string[];
      app_versions: string[];
    }>;
  };
};

export const SITE_DEEP_SCAN_STORAGE_KEY = "ga4-ai-deep-scan-site:last-report:v1";
export const GAME_DEEP_SCAN_STORAGE_KEY = "ga4-ai-deep-scan-game:last-report:v1";

export const SITE_DEEP_SCAN_CONFIG: DeepScanConfig = {
  title: "Analyze your site (Deep Scan)",
  description: (
    <>
      A first-run narrative report grounded in your users&apos; journeys.
      Step 1 builds two summary tables from your raw GA4 export. Step 2
      asks the Web Analyst AI to analyze them and describe what buyers,
      non-buyers, and churned users actually do on your site.
    </>
  ),
  storageKey: SITE_DEEP_SCAN_STORAGE_KEY,
  fetchStatus: getMaterializeWebStatus,
  runMaterialize: postMaterializeWeb,
  runScan: () => runWebAgent({ mode: "deep_scan", include_agent_trace: false }),
};

export const GAME_DEEP_SCAN_CONFIG: DeepScanConfig = {
  title: "Analyze your game (Beta Deep Scan)",
  description: (
    <>
      A gameplay and retention report -- not ecommerce or purchases. Step
      1 builds four summary tables from your GA4 / Firebase export
      (sessions, per-level attempts, per-level rollups, per-player
      journeys with D1/D7/D30 retention flags). Step 2 asks the Game
      Analyst AI about retention cliffs, level difficulty, first-session
      patterns, fails / revives, and persistence.
    </>
  ),
  storageKey: GAME_DEEP_SCAN_STORAGE_KEY,
  fetchStatus: getMaterializeGameStatus,
  runMaterialize: postMaterializeGame,
  gameSessionFilters: {
    loadOptions: getGameSessionFilterOptions,
  },
  runScan: (opts) =>
    runGameAgent({
      mode: "deep_scan",
      include_agent_trace: false,
      filter_countries:
        opts?.filter_countries && opts.filter_countries.length
          ? opts.filter_countries
          : undefined,
      filter_app_versions:
        opts?.filter_app_versions && opts.filter_app_versions.length
          ? opts.filter_app_versions
          : undefined,
    }),
};

type Phase =
  | { kind: "idle" }
  | { kind: "loading-status" }
  | { kind: "ready"; status: MaterializeStatusResponse }
  | { kind: "needs-materialize"; status: MaterializeStatusResponse }
  | { kind: "materializing" }
  | {
      kind: "materialized";
      status: MaterializeStatusResponse;
      result: MaterializeResponse;
    }
  | { kind: "scanning" }
  | { kind: "reported"; report: AgentRunResponse }
  | { kind: "error"; message: string; previous: Phase };

type PersistedDeepScanReport = {
  v: 1;
  report: AgentRunResponse;
  savedAt: number;
};

function tablesNeedMaterialize(status: MaterializeStatusResponse): boolean {
  return status.tables.some((t) => !t.exists);
}

function formatBytes(n: number | null | undefined): string {
  if (n == null) return "-";
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)} GB`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)} KB`;
  return `${n} B`;
}

function formatCount(n: number | null | undefined): string {
  if (n == null) return "-";
  return n.toLocaleString();
}


export function DeepScan({ config }: { config: DeepScanConfig }) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [filterOptions, setFilterOptions] = useState<{
    countries: string[];
    app_versions: string[];
  } | null>(null);
  const [filterOptionsError, setFilterOptionsError] = useState<string | null>(
    null
  );
  const [selCountries, setSelCountries] = useState<string[]>([]);
  const [selAppVersions, setSelAppVersions] = useState<string[]>([]);

  // On mount, restore any persisted report or probe status so the user lands
  // on either ``ready`` or ``needs-materialize`` without an extra click.
  useEffect(() => {
    let mounted = true;
    try {
      if (typeof window !== "undefined") {
        const raw = localStorage.getItem(config.storageKey);
        if (raw) {
          const parsed = JSON.parse(raw) as PersistedDeepScanReport;
          if (parsed?.v === 1 && parsed.report?.answer && parsed.report?.request_id) {
            setPhase({ kind: "reported", report: parsed.report });
            return () => {
              mounted = false;
            };
          }
        }
      }
    } catch {
      /* ignore corrupt storage */
    }
    setPhase({ kind: "loading-status" });
    config
      .fetchStatus()
      .then((status) => {
        if (!mounted) return;
        setPhase({
          kind: tablesNeedMaterialize(status) ? "needs-materialize" : "ready",
          status,
        });
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setPhase({
          kind: "error",
          message: (err as Error).message || "Could not load Deep Scan status.",
          previous: { kind: "idle" },
        });
      });
    return () => {
      mounted = false;
    };
  }, [config]);

  useEffect(() => {
    if (!config.gameSessionFilters) {
      setFilterOptions(null);
      setFilterOptionsError(null);
      return;
    }
    let cancelled = false;
    setFilterOptionsError(null);
    config.gameSessionFilters
      .loadOptions()
      .then((o) => {
        if (!cancelled) {
          setFilterOptions({
            countries: o.countries ?? [],
            app_versions: o.app_versions ?? [],
          });
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setFilterOptionsError(
            (e as Error).message ||
              "Could not load country / app version options."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [config]);

  async function handleMaterialize() {
    try {
      localStorage.removeItem(config.storageKey);
    } catch {
      /* ignore */
    }
    setPhase({ kind: "materializing" });
    try {
      const result = await config.runMaterialize();
      const status = await config.fetchStatus();
      setPhase({ kind: "materialized", status, result });
    } catch (err) {
      setPhase({
        kind: "error",
        message: (err as Error).message || "Materialization failed.",
        previous: { kind: "idle" },
      });
    }
  }

  async function handleDeepScan() {
    setPhase({ kind: "scanning" });
    try {
      const report = await config.runScan(
        config.gameSessionFilters
          ? {
              filter_countries: selCountries.length ? selCountries : undefined,
              filter_app_versions: selAppVersions.length
                ? selAppVersions
                : undefined,
            }
          : undefined
      );
      setPhase({ kind: "reported", report });
      try {
        const payload: PersistedDeepScanReport = {
          v: 1,
          report,
          savedAt: Date.now(),
        };
        localStorage.setItem(config.storageKey, JSON.stringify(payload));
      } catch {
        /* ignore quota */
      }
    } catch (err) {
      setPhase({
        kind: "error",
        message: (err as Error).message || "Deep Scan failed.",
        previous: { kind: "idle" },
      });
    }
  }

  function handleReset() {
    try {
      localStorage.removeItem(config.storageKey);
    } catch {
      /* ignore */
    }
    setPhase({ kind: "loading-status" });
    config
      .fetchStatus()
      .then((status) => {
        setPhase({
          kind: tablesNeedMaterialize(status) ? "needs-materialize" : "ready",
          status,
        });
      })
      .catch((err: unknown) => {
        setPhase({
          kind: "error",
          message: (err as Error).message || "Could not reload status.",
          previous: { kind: "idle" },
        });
      });
  }

  const gameSessionFilterPanel = config.gameSessionFilters ? (
    <div className="deep-scan-filters">
      <h3 className="deep-scan-filters-title">Session scope (optional)</h3>
      <p className="hint">
        Filter which sessions are analyzed. A session is included if it matches
        the selected country list (or no country is selected) and the selected
        app version list (or no version is selected), both at session level.
        Leave both lists unselected to scan everything.
      </p>
      {filterOptionsError && (
        <p className="deep-scan-filters-err" role="alert">
          {filterOptionsError}
        </p>
      )}
      {filterOptions && !filterOptionsError && (
        <div className="deep-scan-filter-grid">
          <div>
            <span className="deep-scan-filter-label">Country</span>
            <select
              multiple
              className="deep-scan-multiselect"
              value={selCountries}
              onChange={(e) =>
                setSelCountries(
                  Array.from(e.target.selectedOptions, (o) => o.value)
                )
              }
              size={Math.min(8, Math.max(4, filterOptions.countries.length + 1))}
              aria-label="Countries to include in Deep Scan"
            >
              {filterOptions.countries.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            {filterOptions.countries.length === 0 && (
              <p className="hint">No country values in game_sessions yet.</p>
            )}
          </div>
          <div>
            <span className="deep-scan-filter-label">App version</span>
            <select
              multiple
              className="deep-scan-multiselect"
              value={selAppVersions}
              onChange={(e) =>
                setSelAppVersions(
                  Array.from(e.target.selectedOptions, (o) => o.value)
                )
              }
              size={Math.min(
                8,
                Math.max(4, filterOptions.app_versions.length + 1)
              )}
              aria-label="App versions to include in Deep Scan"
            >
              {filterOptions.app_versions.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
            {filterOptions.app_versions.length === 0 && (
              <p className="hint">No app_version values in game_sessions yet.</p>
            )}
          </div>
        </div>
      )}
    </div>
  ) : null;

  return (
    <section className="deep-scan">
      <h2>{config.title}</h2>
      <p className="hint">{config.description}</p>

      {phase.kind === "loading-status" && (
        <p className="deep-scan-status">Checking Deep Scan readiness...</p>
      )}

      {phase.kind === "ready" && (
        <div className="deep-scan-panel">
          <SummaryTablesBadge status={phase.status} />
          {gameSessionFilterPanel}
          <div className="deep-scan-actions">
            <button
              type="button"
              className="prompt-button deep-scan-primary"
              onClick={handleDeepScan}
            >
              Run Deep Scan
            </button>
            <button
              type="button"
              className="deep-scan-secondary"
              onClick={handleMaterialize}
              title="Rebuild summary tables (discards current tables, then rebuilds)."
            >
              Rebuild summaries
            </button>
          </div>
        </div>
      )}

      {phase.kind === "needs-materialize" && (
        <div className="deep-scan-panel">
          <SummaryTablesBadge status={phase.status} />
          <p className="deep-scan-status">
            Summary tables are not built yet. Build them to enable Deep Scan.
          </p>
          <div className="deep-scan-actions">
            <button
              type="button"
              className="prompt-button deep-scan-primary"
              onClick={handleMaterialize}
            >
              Build summary tables
            </button>
          </div>
        </div>
      )}

      {phase.kind === "materializing" && (
        <p className="deep-scan-status">
          Building summary tables... this scans your raw GA4 export and can
          take up to a minute.
        </p>
      )}

      {phase.kind === "materialized" && (
        <div className="deep-scan-panel">
          <SummaryTablesBadge status={phase.status} />
          <MaterializeStatsPanel result={phase.result} />
          {gameSessionFilterPanel}
          <div className="deep-scan-actions">
            <button
              type="button"
              className="prompt-button deep-scan-primary"
              onClick={handleDeepScan}
            >
              Run Deep Scan
            </button>
          </div>
        </div>
      )}

      {phase.kind === "scanning" && (
        <p className="deep-scan-status">
          Running Deep Scan... the agent is probing the summary tables and
          writing a narrative report (usually 30-90 seconds).
        </p>
      )}

      {phase.kind === "reported" && (
        <div className="deep-scan-panel">
          <div className="deep-scan-meta">
            <span className="agent-log-meta" title={phase.report.request_id}>
              Report <code>{phase.report.request_id.slice(0, 8)}</code>...
            </span>
            <button
              type="button"
              className="deep-scan-secondary"
              onClick={handleReset}
            >
              New Deep Scan
            </button>
          </div>
          {phase.report.cost_summary && (
            <p
              className="agent-log-meta"
              title={phase.report.cost_summary.note}
            >
              BigQuery this run:{" "}
              {phase.report.cost_summary.bigquery.query_count} quer
              {phase.report.cost_summary.bigquery.query_count === 1
                ? "y"
                : "ies"}
              , ~
              {phase.report.cost_summary.bigquery.total_est_cost_usd != null
                ? `$${phase.report.cost_summary.bigquery.total_est_cost_usd.toFixed(4)}`
                : "-"}{" "}
              est. (on-demand $/TB assumption)
            </p>
          )}
          <AnswerRenderer markdown={phase.report.answer} />
        </div>
      )}

      {phase.kind === "error" && (
        <div className="deep-scan-panel">
          <p className="form-error">Deep Scan error: {phase.message}</p>
          <div className="deep-scan-actions">
            <button
              type="button"
              className="deep-scan-secondary"
              onClick={handleReset}
            >
              Retry
            </button>
          </div>
        </div>
      )}
    </section>
  );
}


function SummaryTablesBadge({ status }: { status: MaterializeStatusResponse }) {
  return (
    <ul className="deep-scan-tables">
      {status.tables.map((t) => (
        <li key={t.name} className="deep-scan-table-row">
          <code>{t.name}</code>
          {t.exists ? (
            <>
              <span className="chip chip-ok">ready</span>
              <span className="deep-scan-table-meta">
                {formatCount(t.row_count)} rows
                {t.last_modified
                  ? ` - built ${new Date(t.last_modified).toLocaleString()}`
                  : ""}
              </span>
            </>
          ) : (
            <span className="chip chip-warn">not built</span>
          )}
        </li>
      ))}
    </ul>
  );
}


function MaterializeStatsPanel({ result }: { result: MaterializeResponse }) {
  return (
    <div className="deep-scan-mat-stats">
      <p>
        Window: {result.window.start} to {result.window.end} (
        {result.window.days} days). Groups labelled with{" "}
        new&lt;={result.cutoffs.new_cutoff_days}d,{" "}
        active&lt;={result.cutoffs.churn_cutoff_days}d.
      </p>
      <ul>
        {result.tables.map((t) => (
          <li key={t.table}>
            <code>{t.table}</code>: {formatCount(t.rows)} rows,{" "}
            {formatBytes(t.bytes_billed)} billed, {t.elapsed_ms} ms.
            {t.est_cost_usd != null && t.est_cost_usd > 0 && (
              <> (~${t.est_cost_usd.toFixed(4)} est.)</>
            )}
            {t.bytes_billed_pct_of_cap != null && (
              <> ({t.bytes_billed_pct_of_cap}% of per-job cap)</>
            )}
          </li>
        ))}
        <li>
          <strong>Total billed:</strong> {formatBytes(result.total_bytes_billed)}
          {result.cost_estimate?.total_est_cost_usd != null && (
            <>
              {" "}
              (~${result.cost_estimate.total_est_cost_usd.toFixed(4)} est.
              on-demand)
            </>
          )}
        </li>
      </ul>
    </div>
  );
}
