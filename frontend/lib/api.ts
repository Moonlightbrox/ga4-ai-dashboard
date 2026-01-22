// This file defines typed API helpers for the frontend to talk to the backend.
// It centralizes fetch handling and shared response/request shapes.

export type ReportRow = Record<string, unknown>;                             // Generic row shape for report tables.

export type ReportSchemaItem = {
  id: string;                                                                // GA4 metric/dimension identifier.
  label: string;                                                             // Human-friendly label for UI display.
  description: string;                                                       // Short description shown in the UI.
};

export type ReportPayload = {
  id: string;                                                                // Stable report identifier.
  name: string;                                                              // Report display name.
  description: string;                                                       // Report description shown in UI.
  data: ReportRow[];                                                         // Report rows as key/value maps.
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";                 // Backend base URL for API calls.

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

export async function fetchReportSchema() {
  return request<{ metrics: ReportSchemaItem[]; dimensions: ReportSchemaItem[] }>(
    "/api/reports/schema"
  );
}

export async function createCustomReport(payload: {
  start_date: string;                                                        // Report window start date (YYYY-MM-DD).
  end_date: string;                                                          // Report window end date (YYYY-MM-DD).
  metrics: string[];                                                         // Selected GA4 metric IDs.
  dimensions: string[];                                                      // Selected GA4 dimension IDs.
}) {
  return request<{ data: ReportRow[] }>("/api/reports/custom", {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
  selected_reports: ReportPayload[];                                         // Reports included in the AI prompt.
  user_question: string;                                                     // Question to ask the AI.
  prompt_key?: string | null;                                                // Optional prompt template key.
  coverage_pct: number;                                                      // Percent of rows to include per report.
}) {
  return request<{ answer: string }>("/api/ai/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
