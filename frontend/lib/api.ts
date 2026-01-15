export type ReportRow = Record<string, unknown>;

export type ReportPayload = {
  id: string;
  name: string;
  description: string;
  data: ReportRow[];
};

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

export async function fetchCoreReports(start: string, end: string) {
  return request<{ reports: ReportPayload[] }>(
    `/api/reports/core?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
  );
}

export async function fetchAuthStatus() {
  return request<{ connected: boolean }>("/api/auth/status");
}

export async function fetchProperties() {
  return request<{ properties: { property_id: string; display_name: string }[] }>(
    "/api/ga4/properties"
  );
}

export async function selectProperty(propertyId: string) {
  return request<{ selected: string }>("/api/ga4/select-property", {
    method: "POST",
    body: JSON.stringify({ property_id: propertyId }),
  });
}

export async function runAnalysis(payload: {
  selected_reports: ReportPayload[];
  user_question: string;
  prompt_key?: string | null;
  coverage_pct: number;
}) {
  return request<{ answer: string }>("/api/ai/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
