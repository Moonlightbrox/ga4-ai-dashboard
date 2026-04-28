"use client";

/**
 * AgentChat -- the unified ask-anything UI.
 *
 * Lets the user pick which agent to ask (Web or Game), type any
 * free-form question, and submit. The response is rendered with the
 * shared :func:`AnswerRenderer`, so a question typed here that matches
 * a Deep Scan prompt produces the same formatting and shape as the
 * Deep Scan button. For the Game agent the user can optionally pick
 * countries / app versions to slice the analysis.
 *
 * History is persisted to ``localStorage`` so it survives a refresh
 * (just like the Deep Scan reports), but it is *not* sent back to the
 * agent on the next turn -- each call to ``runWebAgent`` /
 * ``runGameAgent`` is a fresh, context-free request. The persistence
 * is purely a UX nicety; the orchestrator prompt remains the only
 * source of context for the model.
 */

import { useEffect, useRef, useState } from "react";

import {
  getGameSessionFilterOptions,
  runGameAgent,
  runWebAgent,
  type AgentRunResponse,
} from "../lib/api";
import { AnswerRenderer } from "./AnswerRenderer";


type AgentId = "web" | "game";

type ChatTurn = {
  id: string;
  agent: AgentId;
  question: string;
  filterCountries: string[];
  filterAppVersions: string[];
  pending: boolean;
  response?: AgentRunResponse;
  error?: string;
};

const CHAT_STORAGE_KEY = "ga4-ai-agent-chat:turns:v1";

type PersistedChatV1 = {
  v: 1;
  savedAt: number;
  turns: ChatTurn[];
};

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

function loadPersistedTurns(): ChatTurn[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as PersistedChatV1;
    if (!parsed || parsed.v !== 1 || !Array.isArray(parsed.turns)) return [];
    // Pending turns were in flight when the page closed; we have no way to
    // resume them, so drop them rather than leave the user staring at a
    // permanent "Thinking..." spinner.
    return parsed.turns.filter((t) => t && !t.pending);
  } catch {
    return [];
  }
}

function savePersistedTurns(turns: ChatTurn[]): void {
  if (typeof window === "undefined") return;
  try {
    const payload: PersistedChatV1 = {
      v: 1,
      savedAt: Date.now(),
      turns: turns.map((t) => ({ ...t, pending: false })),
    };
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* quota exceeded or storage unavailable; keep in-memory state */
  }
}


export function AgentChat() {
  const [agent, setAgent] = useState<AgentId>("web");
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [filterOptions, setFilterOptions] = useState<{
    countries: string[];
    app_versions: string[];
  } | null>(null);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [selCountries, setSelCountries] = useState<string[]>([]);
  const [selAppVersions, setSelAppVersions] = useState<string[]>([]);

  // Skip the very first persistence write so we don't immediately overwrite a
  // (possibly larger) saved payload with the empty initial state. Only writes
  // triggered by genuine user actions (ask / clear) should hit storage.
  const hydratedRef = useRef(false);

  useEffect(() => {
    const persisted = loadPersistedTurns();
    if (persisted.length > 0) {
      setTurns(persisted);
    }
    hydratedRef.current = true;
  }, []);

  useEffect(() => {
    if (!hydratedRef.current) return;
    savePersistedTurns(turns);
  }, [turns]);

  useEffect(() => {
    if (agent !== "game") return;
    if (filterOptions || filterError) return;
    let cancelled = false;
    getGameSessionFilterOptions()
      .then((o) => {
        if (cancelled) return;
        setFilterOptions({
          countries: o.countries ?? [],
          app_versions: o.app_versions ?? [],
        });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setFilterError(
          (e as Error).message ||
            "Could not load game session filter options."
        );
      });
    return () => {
      cancelled = true;
    };
  }, [agent, filterOptions, filterError]);

  async function handleSubmit() {
    const q = question.trim();
    if (!q || submitting) return;
    const turnId = newId();
    const optimisticTurn: ChatTurn = {
      id: turnId,
      agent,
      question: q,
      filterCountries: agent === "game" ? [...selCountries] : [],
      filterAppVersions: agent === "game" ? [...selAppVersions] : [],
      pending: true,
    };
    setTurns((prev) => [...prev, optimisticTurn]);
    setQuestion("");
    setSubmitting(true);
    try {
      const response =
        agent === "web"
          ? await runWebAgent({
              mode: "chat",
              user_question: q,
              include_agent_trace: false,
            })
          : await runGameAgent({
              mode: "chat",
              user_question: q,
              include_agent_trace: false,
              filter_countries: selCountries.length ? selCountries : undefined,
              filter_app_versions: selAppVersions.length
                ? selAppVersions
                : undefined,
            });
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId ? { ...t, pending: false, response } : t
        )
      );
    } catch (err) {
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId
            ? {
                ...t,
                pending: false,
                error: (err as Error).message || "Agent run failed.",
              }
            : t
        )
      );
    } finally {
      setSubmitting(false);
    }
  }

  function handleClear() {
    if (turns.length === 0) return;
    const plural = turns.length === 1 ? "" : "s";
    const ok = window.confirm(
      `Clear ${turns.length} saved chat turn${plural}? This cannot be undone.`
    );
    if (!ok) return;
    setTurns([]);
    try {
      localStorage.removeItem(CHAT_STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }

  return (
    <section className="agent-chat">
      <h2>Ask an analyst</h2>
      <p className="hint">
        Pick which AI to ask, then type a question. Anything you ask here is
        answered by the same agent that powers the Deep Scan buttons -- if
        you paste a Deep Scan prompt verbatim you will get an equivalent
        report. Each turn is a fresh agent run; chat history is not sent
        back to the model.
      </p>

      <div className="agent-chat-controls">
        <fieldset className="agent-picker">
          <legend>Analyst</legend>
          <label className="agent-picker-option">
            <input
              type="radio"
              name="agent"
              value="web"
              checked={agent === "web"}
              onChange={() => setAgent("web")}
            />
            <span>Web Analyst</span>
          </label>
          <label className="agent-picker-option">
            <input
              type="radio"
              name="agent"
              value="game"
              checked={agent === "game"}
              onChange={() => setAgent("game")}
            />
            <span>Game Analyst</span>
          </label>
        </fieldset>

        {agent === "game" && (
          <details className="agent-chat-filters">
            <summary>Session scope (optional)</summary>
            <p className="hint">
              Filter which sessions the Game Analyst sees. Leave both empty
              to scan everything.
            </p>
            {filterError && (
              <p className="form-error" role="alert">
                {filterError}
              </p>
            )}
            {filterOptions && !filterError && (
              <div className="deep-scan-filter-grid">
                <div>
                  <span className="deep-scan-filter-label">Country</span>
                  <select
                    multiple
                    className="deep-scan-multiselect"
                    value={selCountries}
                    onChange={(e) =>
                      setSelCountries(
                        Array.from(
                          e.target.selectedOptions,
                          (o) => o.value
                        )
                      )
                    }
                    size={Math.min(
                      8,
                      Math.max(4, filterOptions.countries.length + 1)
                    )}
                    aria-label="Countries to include"
                  >
                    {filterOptions.countries.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <span className="deep-scan-filter-label">App version</span>
                  <select
                    multiple
                    className="deep-scan-multiselect"
                    value={selAppVersions}
                    onChange={(e) =>
                      setSelAppVersions(
                        Array.from(
                          e.target.selectedOptions,
                          (o) => o.value
                        )
                      )
                    }
                    size={Math.min(
                      8,
                      Math.max(4, filterOptions.app_versions.length + 1)
                    )}
                    aria-label="App versions to include"
                  >
                    {filterOptions.app_versions.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </details>
        )}
      </div>

      <div className="agent-chat-input">
        <textarea
          className="agent-chat-textarea"
          rows={4}
          placeholder={
            agent === "web"
              ? "Ask the Web Analyst about your site... e.g. 'What do non-buyers do before they leave?'"
              : "Ask the Game Analyst... e.g. 'Where do new players churn in the first session?'"
          }
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              void handleSubmit();
            }
          }}
        />
        <div className="agent-chat-actions">
          <button
            type="button"
            className="prompt-button"
            disabled={!question.trim() || submitting}
            onClick={() => void handleSubmit()}
          >
            {submitting ? "Running..." : "Ask"}
          </button>
          <span className="hint">Cmd/Ctrl + Enter to submit.</span>
        </div>
      </div>

      <div className="agent-chat-history">
        {turns.length === 0 ? (
          <p className="hint">No questions yet.</p>
        ) : (
          <>
            <div className="agent-chat-history-head">
              <span className="hint">
                {turns.length} turn{turns.length === 1 ? "" : "s"} saved
              </span>
              <button
                type="button"
                className="deep-scan-secondary"
                onClick={handleClear}
              >
                Clear chat
              </button>
            </div>
            {turns
              .slice()
              .reverse()
              .map((turn) => (
              <article key={turn.id} className="agent-chat-turn">
                <header className="agent-chat-turn-head">
                  <span className="agent-chat-turn-agent">
                    {turn.agent === "web" ? "Web Analyst" : "Game Analyst"}
                  </span>
                  {(turn.filterCountries.length > 0 ||
                    turn.filterAppVersions.length > 0) && (
                    <span className="agent-chat-turn-scope">
                      scope:{" "}
                      {turn.filterCountries.length > 0 &&
                        `countries=${turn.filterCountries.join(", ")}`}
                      {turn.filterCountries.length > 0 &&
                      turn.filterAppVersions.length > 0
                        ? "; "
                        : ""}
                      {turn.filterAppVersions.length > 0 &&
                        `versions=${turn.filterAppVersions.join(", ")}`}
                    </span>
                  )}
                </header>
                <p className="agent-chat-turn-question">{turn.question}</p>
                {turn.pending && (
                  <p className="deep-scan-status">Thinking...</p>
                )}
                {turn.error && (
                  <p className="form-error" role="alert">
                    {turn.error}
                  </p>
                )}
                {turn.response && (
                  <>
                    {turn.response.cost_summary && (
                      <p
                        className="agent-log-meta"
                        title={turn.response.cost_summary.note}
                      >
                        BigQuery this turn:{" "}
                        {turn.response.cost_summary.bigquery.query_count}{" "}
                        quer
                        {turn.response.cost_summary.bigquery.query_count === 1
                          ? "y"
                          : "ies"}
                        , ~
                        {turn.response.cost_summary.bigquery
                          .total_est_cost_usd != null
                          ? `$${turn.response.cost_summary.bigquery.total_est_cost_usd.toFixed(4)}`
                          : "-"}{" "}
                        est.
                      </p>
                    )}
                    <AnswerRenderer markdown={turn.response.answer} />
                  </>
                )}
              </article>
            ))}
          </>
        )}
      </div>
    </section>
  );
}
