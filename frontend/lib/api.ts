// Typed API helpers for the BigQuery analyst frontend.
// Centralises fetch handling and shared response shapes so components can
// stay UI-only.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const message = await res.text();
    throw new Error(message || `Request failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Auth + GA4 property selection
// ---------------------------------------------------------------------------

export type Property = {
  property_id: string;
  display_name: string;
};

export async function fetchAuthStatus() {
  return request<{ connected: boolean }>("/api/auth/status");
}

export async function fetchProperties() {
  return request<{ properties: Property[] }>("/api/ga4/properties");
}

export async function selectProperty(propertyId: string) {
  return request<{ selected: string }>("/api/ga4/select-property", {
    method: "POST",
    body: JSON.stringify({ property_id: propertyId }),
  });
}

// ---------------------------------------------------------------------------
// GA4 -> BigQuery managed export link
// ---------------------------------------------------------------------------

export type BigQueryLinkInfo = {
  name: string;
  project: string;
  dataset_location: string;
  daily_export_enabled: boolean;
  streaming_export_enabled: boolean;
  export_streams: string[];
};

export type LinkBigQueryResponse = {
  grant: { status: string; name?: string };
  bigquery_link: {
    status: string;
    name?: string;
    project?: string;
    export_streams?: string[];
    export_streams_updated?: boolean;
    export_streams_update_error?: string;
  };
  export_streams: string[];
  export_dataset_id_hint: string;
  gcp_project_id: string;
  message: string;
};

export async function linkBigQueryExport(options?: { streaming_export?: boolean }) {
  return request<LinkBigQueryResponse>("/api/bigquery/link", {
    method: "POST",
    body: JSON.stringify({ streaming_export: options?.streaming_export ?? false }),
  });
}

export async function fetchBigQueryLinkStatus() {
  return request<{ property_id: string; bigquery_links: BigQueryLinkInfo[] }>(
    "/api/bigquery/link-status"
  );
}

// ---------------------------------------------------------------------------
// Materialization (web + game summary tables)
// ---------------------------------------------------------------------------

export type MaterializeTableStat = {
  table: string;
  rows: number | null;
  bytes_billed: number | null;
  bytes_processed: number | null;
  elapsed_ms: number;
  est_cost_usd?: number | null;
  bytes_billed_pct_of_cap?: number | null;
};

export type MaterializeCostEstimate = {
  total_est_cost_usd: number | null;
  total_bytes_billed: number;
  usd_per_tb_assumed: number;
  max_bytes_billed_per_job: number;
  note: string;
};

export type MaterializeResponse = {
  property_id: string;
  ok: true;
  dataset_ref: string;
  window: { start: string; end: string; days: number };
  cutoffs: { new_cutoff_days: number; churn_cutoff_days: number };
  tables: MaterializeTableStat[];
  total_bytes_billed: number;
  warning?: string;
  cost_estimate?: MaterializeCostEstimate;
};

export type MaterializeTableStatus =
  | { name: string; exists: false }
  | {
      name: string;
      exists: true;
      last_modified: string | null;
      row_count: number | null;
    };

export type MaterializeStatusResponse = {
  property_id: string;
  dataset_ref: string;
  tables: MaterializeTableStatus[];
};

export async function postMaterializeWeb(payload?: { days?: number }) {
  return request<MaterializeResponse>("/api/bigquery/materialize-web", {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export async function getMaterializeWebStatus() {
  return request<MaterializeStatusResponse>(
    "/api/bigquery/materialize-web/status"
  );
}

export async function postMaterializeGame(payload?: { days?: number }) {
  return request<MaterializeResponse>("/api/bigquery/materialize-game", {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export async function getMaterializeGameStatus() {
  return request<MaterializeStatusResponse>(
    "/api/bigquery/materialize-game/status"
  );
}

export type GameFilterOptionsResponse = {
  property_id: string;
  dataset_ref: string;
  countries: string[];
  app_versions: string[];
};

export async function getGameSessionFilterOptions() {
  return request<GameFilterOptionsResponse>(
    "/api/bigquery/materialize-game/filter-options"
  );
}

// ---------------------------------------------------------------------------
// Agents (Web Analyst + Game Analyst)
// ---------------------------------------------------------------------------

export type AgentTraceEvent = Record<string, unknown>;

export type AgentBigQueryCost = {
  query_count: number;
  total_bytes_billed: number;
  total_est_cost_usd: number | null;
  max_bytes_billed_cap: number;
  usd_per_tb_assumed: number;
  per_query: Array<{
    seq: number;
    step: number;
    intent: string | null | undefined;
    bytes_billed: number;
    est_cost_usd: number | null;
    bytes_billed_pct_of_cap: number | null;
  }>;
};

export type AgentCostSummary = {
  bigquery: AgentBigQueryCost;
  note: string;
};

export type AgentRunResponse = {
  property_id: string;
  answer: string;
  request_id: string;
  cost_summary: AgentCostSummary;
  agent_trace?: AgentTraceEvent[];
};

export type AgentMode = "deep_scan" | "chat";

export async function runWebAgent(payload: {
  mode: AgentMode;
  user_question?: string | null;
  include_agent_trace?: boolean;
}) {
  const body = {
    mode: payload.mode,
    user_question: payload.user_question ?? null,
    include_agent_trace: payload.include_agent_trace ?? false,
  };
  return request<AgentRunResponse>("/api/agents/web/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function runGameAgent(payload: {
  mode: AgentMode;
  user_question?: string | null;
  include_agent_trace?: boolean;
  filter_countries?: string[] | null;
  filter_app_versions?: string[] | null;
}) {
  const body: Record<string, unknown> = {
    mode: payload.mode,
    user_question: payload.user_question ?? null,
    include_agent_trace: payload.include_agent_trace ?? false,
  };
  if (payload.filter_countries && payload.filter_countries.length > 0) {
    body.filter_countries = payload.filter_countries;
  }
  if (payload.filter_app_versions && payload.filter_app_versions.length > 0) {
    body.filter_app_versions = payload.filter_app_versions;
  }
  return request<AgentRunResponse>("/api/agents/game/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type AgentPromptCatalog = {
  agents: Array<{
    id: "web" | "game";
    label: string;
    system_prompt: string;
    orchestrator_prompt: string;
  }>;
};

export async function fetchAgentPrompts() {
  return request<AgentPromptCatalog>("/api/agents/prompts");
}
