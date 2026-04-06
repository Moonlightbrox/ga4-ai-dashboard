// Browser-local overrides for AI system and template prompts (sent with each analyze request).

const TEMPLATE_OVERRIDES_KEY = "ga4-ai-prompt-overrides:v1";
const SYSTEM_OVERRIDE_KEY = "ga4-ai-system-prompt-override:v1";

export function loadTemplateOverrides(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(TEMPLATE_OVERRIDES_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    return parsed as Record<string, string>;
  } catch {
    return {};
  }
}

export function upsertTemplateOverride(key: string, body: string, defaultBody: string) {
  if (typeof window === "undefined") return;
  try {
    const ov = { ...loadTemplateOverrides() };
    if (body === defaultBody) {
      delete ov[key];
    } else {
      ov[key] = body;
    }
    if (Object.keys(ov).length === 0) {
      localStorage.removeItem(TEMPLATE_OVERRIDES_KEY);
    } else {
      localStorage.setItem(TEMPLATE_OVERRIDES_KEY, JSON.stringify(ov));
    }
  } catch {
    /* quota */
  }
}

export function loadSystemOverride(): string | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const s = localStorage.getItem(SYSTEM_OVERRIDE_KEY);
    return s ?? undefined;
  } catch {
    return undefined;
  }
}

export function saveSystemOverride(body: string | undefined, defaultSystem: string) {
  if (typeof window === "undefined") return;
  try {
    if (!body || body === defaultSystem) {
      localStorage.removeItem(SYSTEM_OVERRIDE_KEY);
    } else {
      localStorage.setItem(SYSTEM_OVERRIDE_KEY, body);
    }
  } catch {
    /* quota */
  }
}

/** Fields to merge into /api/ai/analyze when the user has local overrides. */
export function getAnalysisPromptExtras(promptKey: string | null | undefined): {
  prompt_template_override?: string;
  system_prompt_override?: string;
} {
  const out: { prompt_template_override?: string; system_prompt_override?: string } = {};
  const sys = loadSystemOverride();
  if (sys && sys.trim()) {
    out.system_prompt_override = sys;
  }
  if (promptKey) {
    const ov = loadTemplateOverrides()[promptKey];
    if (ov && ov.trim()) {
      out.prompt_template_override = ov;
    }
  }
  return out;
}
