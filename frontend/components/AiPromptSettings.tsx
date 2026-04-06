"use client";

import { useEffect, useState } from "react";
import { fetchPromptCatalog, type PromptCatalog } from "../lib/api";
import {
  loadSystemOverride,
  loadTemplateOverrides,
  saveSystemOverride,
  upsertTemplateOverride,
} from "../lib/promptStorage";

type Props = {
  className?: string;
};

export function AiPromptSettings({ className }: Props) {
  const [catalog, setCatalog] = useState<PromptCatalog | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [systemDraft, setSystemDraft] = useState("");
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, string>>({});

  useEffect(() => {
    let mounted = true;
    fetchPromptCatalog()
      .then((data) => {
        if (!mounted) return;
        setCatalog(data);
        setLoadError(null);
        const savedSys = loadSystemOverride();
        setSystemDraft(savedSys ?? data.agent_system_prompt);
        const ov = loadTemplateOverrides();
        const next: Record<string, string> = {};
        for (const t of data.templates) {
          next[t.key] = ov[t.key] ?? t.default_body;
        }
        setTemplateDrafts(next);
      })
      .catch((err) => {
        if (mounted) setLoadError((err as Error).message);
      });
    return () => {
      mounted = false;
    };
  }, []);

  function persistSystem() {
    if (!catalog) return;
    saveSystemOverride(systemDraft, catalog.agent_system_prompt);
  }

  function resetSystem() {
    if (!catalog) return;
    if (!window.confirm("Reset the agent system prompt to the built-in default?")) return;
    saveSystemOverride(undefined, catalog.agent_system_prompt);
    setSystemDraft(catalog.agent_system_prompt);
  }

  function persistTemplate(key: string, defaultBody: string) {
    const body = templateDrafts[key] ?? "";
    upsertTemplateOverride(key, body, defaultBody);
  }

  function resetTemplate(key: string, defaultBody: string) {
    setTemplateDrafts((prev) => ({ ...prev, [key]: defaultBody }));
    upsertTemplateOverride(key, defaultBody, defaultBody);
  }

  if (loadError) {
    return (
      <section className={className}>
        <details className="ai-prompt-settings">
          <summary>AI prompt settings</summary>
          <p className="form-error">Could not load prompt catalog: {loadError}</p>
        </details>
      </section>
    );
  }

  if (!catalog) {
    return (
      <section className={className}>
        <details className="ai-prompt-settings">
          <summary>AI prompt settings</summary>
          <p>Loading defaults from the server…</p>
        </details>
      </section>
    );
  }

  return (
    <section className={className}>
      <details className="ai-prompt-settings">
        <summary>AI prompt settings</summary>
        <p className="ai-prompt-settings-hint">
          Defaults come from the server. Edits are saved in this browser only (localStorage) and are sent with each AI
          request. Use <code>{"{USER_QUESTION}"}</code> in templates where the task should include the user&apos;s text
          (quick prompts and insight follow-ups).
        </p>

        <div className="ai-prompt-block">
          <div className="ai-prompt-block-head">
            <h3>Agent system prompt</h3>
            <div className="ai-prompt-block-actions">
              <button type="button" className="chat-actions-secondary" onClick={resetSystem}>
                Reset to default
              </button>
            </div>
          </div>
          <textarea
            className="ai-prompt-textarea ai-prompt-textarea-system"
            value={systemDraft}
            onChange={(e) => setSystemDraft(e.target.value)}
            onBlur={persistSystem}
            spellCheck={false}
          />
        </div>

        {catalog.templates.map((t) => (
          <div key={t.key} className="ai-prompt-block">
            <div className="ai-prompt-block-head">
              <h3>{t.label}</h3>
              <span className="ai-prompt-key">
                <code>{t.key}</code>
              </span>
              <div className="ai-prompt-block-actions">
                <button type="button" className="chat-actions-secondary" onClick={() => resetTemplate(t.key, t.default_body)}>
                  Reset to default
                </button>
              </div>
            </div>
            <textarea
              className="ai-prompt-textarea"
              value={templateDrafts[t.key] ?? t.default_body}
              onChange={(e) =>
                setTemplateDrafts((prev) => ({
                  ...prev,
                  [t.key]: e.target.value,
                }))
              }
              onBlur={() => persistTemplate(t.key, t.default_body)}
              spellCheck={false}
            />
          </div>
        ))}
      </details>
    </section>
  );
}
