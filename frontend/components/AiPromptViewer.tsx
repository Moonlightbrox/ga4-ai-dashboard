"use client";

/**
 * AiPromptViewer -- read-only inspector for the agent prompt catalog.
 *
 * The previous editor allowed in-browser overrides via localStorage; that
 * footgun is gone now. Prompts are owned by the backend (see
 * ``backend/agents/prompts.py``) and are served verbatim by
 * ``GET /api/agents/prompts`` so the UI can show what the AIs are
 * actually running with -- never an out-of-date local copy.
 */

import { useEffect, useState } from "react";

import { fetchAgentPrompts, type AgentPromptCatalog } from "../lib/api";


export function AiPromptViewer() {
  const [catalog, setCatalog] = useState<AgentPromptCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open || catalog || error) return;
    let cancelled = false;
    fetchAgentPrompts()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            (e as Error).message || "Could not load agent prompt catalog."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, catalog, error]);

  return (
    <details
      className="ai-prompt-settings"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary>Agent prompts (read-only)</summary>
      <p className="ai-prompt-settings-hint">
        These are the system prompts and Deep Scan orchestrator prompts the
        Web and Game analysts are running with right now, served straight
        from the backend. Edit them in <code>backend/agents/prompts.py</code>.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {catalog && (
        <div>
          {catalog.agents.map((agent) => (
            <div key={agent.id} className="ai-prompt-block">
              <div className="ai-prompt-block-head">
                <h3>{agent.label}</h3>
                <span className="ai-prompt-key">id: {agent.id}</span>
              </div>
              <details className="ai-prompt-subblock" open>
                <summary>System prompt</summary>
                <pre className="ai-prompt-pre">{agent.system_prompt}</pre>
              </details>
              <details className="ai-prompt-subblock">
                <summary>Deep Scan orchestrator prompt</summary>
                <pre className="ai-prompt-pre">
                  {agent.orchestrator_prompt}
                </pre>
              </details>
            </div>
          ))}
        </div>
      )}
      {!catalog && !error && open && (
        <p className="hint">Loading prompts...</p>
      )}
    </details>
  );
}
