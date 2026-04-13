// This file defines the main GA4 AI dashboard page and its client-side logic. It manages
// report loading, report selection, and the AI Q&A interface that uses those reports.
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchAuthStatus,
  fetchCoreReports,
  fetchProperties,
  fetchReportSchema,
  createCustomReport,
  selectProperty,
  linkBigQueryExport,
  runAnalysis,
  type AgentTraceEvent,
  type ReportPayload,
  type ReportSchemaItem,
} from "../lib/api";
import { AiPromptSettings } from "../components/AiPromptSettings";
import { exportToCSV } from "../lib/exportCsv";
import { getAnalysisPromptExtras } from "../lib/promptStorage";

const UI_STORAGE_KEY = "ga4-ai-dashboard:v1";
const UI_STORAGE_KEY_LEGACY = "ga4-ai-dashboard:v2";

type PersistedUiV1 = {
  v: 1;
  question: string;
  answer: string | null;
  agentLog: { request_id: string; agent_trace: AgentTraceEvent[] } | null;
  savedAt: number;
};

type PersistedUiV2 = {
  v: 2;
  selectedPropertyId: string;
  startDate: string;
  endDate: string;
  reports: ReportPayload[];
  selectedReportIds: string[];
  selectedDimensions: string[];
  selectedMetrics: string[];
  customReportName: string;
  customReportGroup: string;
  question: string;
  answer: string | null;
  agentLog: { request_id: string; agent_trace: AgentTraceEvent[] } | null;
  savedAt: number;
};

function formatDateInput(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultDateRange() {
  const today = new Date();
  const prior = new Date(today);
  prior.setDate(today.getDate() - 30);
  return { start: formatDateInput(prior), end: formatDateInput(today) };
}

function hasSessionDataToPersist(state: {
  selectedPropertyId: string;
  reports: ReportPayload[];
  question: string;
  answer: string | null;
  agentLog: { request_id: string; agent_trace: AgentTraceEvent[] } | null;
  selectedDimensions: string[];
  selectedMetrics: string[];
  customReportName: string;
  customReportGroup: string;
}): boolean {
  return (
    Boolean(state.selectedPropertyId.trim()) ||
    state.reports.length > 0 ||
    state.question.trim().length > 0 ||
    state.answer != null ||
    state.agentLog != null ||
    state.selectedDimensions.length > 0 ||
    state.selectedMetrics.length > 0 ||
    Boolean(state.customReportName.trim()) ||
    Boolean(state.customReportGroup.trim())
  );
}

/* =============================================================================
 * Main Page Component: stateful dashboard with report loading and AI chat
 * =============================================================================
 */

// Renders the primary dashboard view and wires up report/AI interactions.
export default function HomePage() {
  /* -------------------------------------------------------------------------
   * State setup for filters, report data, and AI interactions
   * -------------------------------------------------------------------------
   */
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";                 // Base URL for auth redirects to the backend.
  const [startDate, setStartDate] = useState(() => defaultDateRange().start); // Start date for report queries.
  const [endDate, setEndDate] = useState(() => defaultDateRange().end);       // End date for report queries.
  const [reports, setReports] = useState<ReportPayload[]>([]);                // Loaded report payloads from the API.
  const [selectedReportIds, setSelectedReportIds] = useState<string[]>([]);   // IDs of reports selected for tables/AI.
  const [connected, setConnected] = useState(false);                          // Current OAuth connection status.
  const [properties, setProperties] = useState<                               // GA4 properties available to the user.
    { property_id: string; display_name: string }[]
  >([]);
  const [selectedPropertyId, setSelectedPropertyId] = useState("");           // Active GA4 property id selection.
  const [status, setStatus] = useState<string | null>(null);                  // Status/error message for UI feedback.
  const [question, setQuestion] = useState("");                               // Free-form AI question text.
  const [answer, setAnswer] = useState<string | null>(null);                  // Latest AI answer text.
  const [agentLog, setAgentLog] = useState<{
    request_id: string;
    agent_trace: AgentTraceEvent[];
  } | null>(null);                                                           // Structured agent events for the last run.
  const [isAsking, setIsAsking] = useState(false);                            // Whether an AI request is in flight.
  const [reportSchema, setReportSchema] = useState<{
    metrics: ReportSchemaItem[];
    dimensions: ReportSchemaItem[];
  } | null>(null);                                                            // Metric/dimension metadata for custom reports.
  const [schemaError, setSchemaError] = useState<string | null>(null);        // Error message when schema fetch fails.
  const [selectedDimensions, setSelectedDimensions] = useState<string[]>([]); // Chosen dimension ids for custom reports.
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([]);       // Chosen metric ids for custom reports.
  const [customReportName, setCustomReportName] = useState("");               // Optional name for a custom report.
  const [customReportGroup, setCustomReportGroup] = useState("");             // Optional group label for a custom report.
  const [customReportError, setCustomReportError] = useState<string | null>(null); // Error message for custom report creation.
  const [customReportSuccess, setCustomReportSuccess] = useState<string | null>(null); // Success message for custom report creation.
  const [isCreatingReport, setIsCreatingReport] = useState(false);            // Whether a custom report request is in flight.
  const [persistReady, setPersistReady] = useState(false);                    // True after localStorage restore has run (avoids clobbering).
  const [bqLinkMessage, setBqLinkMessage] = useState<string | null>(null);    // Managed BigQuery export status or error.
  const [bqLinkLoading, setBqLinkLoading] = useState(false);                  // BigQuery link request in flight.
  const [bqStreaming, setBqStreaming] = useState(false);                      // Optional streaming export when linking.

  const promptButtons = [                                                     // Prebuilt prompt options mapped to backend.
    { key: "traffic_quality_assessment", label: "Traffic quality assessment" },
    { key: "conversion_funnel_leakage", label: "Conversion funnel leakage" },
    { key: "landing_page_optimization", label: "Landing page optimization" },
  ];

  /* -------------------------------------------------------------------------
   * Initial auth/property loading
   * -------------------------------------------------------------------------
   */
  useEffect(() => {
    let mounted = true;                                                       // Track mount state to avoid stale updates.
    fetchAuthStatus()
      .then((result) => {
        if (!mounted) return;                                                 // Skip updates when component unmounts.
        setConnected(result.connected);                                       // Store OAuth connection state.
        if (result.connected) {
          return fetchProperties();                                           // Fetch properties only after auth success.
        }
        return null;                                                          // Return null when no properties are needed.
      })
      .then((result) => {
        if (!mounted || !result) return;                                      // Avoid updates if unmounted or no data.
        setProperties(result.properties);                                     // Store available GA4 properties.
      })
      .catch((err) => {                                                       // Handle network/auth errors during preload.
        if (mounted) {
          setStatus((err as Error).message);                                  // Surface preload errors to the user.
        }
      });
    return () => {                                                            // Cleanup to prevent setState after unmount.
      mounted = false;                                                        // Mark component as unmounted.
    };
  }, []);

  useEffect(() => {
    let mounted = true;                                                       // Track mount state to avoid stale updates.
    fetchReportSchema()
      .then((result) => {
        if (!mounted) return;                                                 // Skip updates when component unmounts.
        setReportSchema(result);                                              // Store schema for the custom report builder.
        setSchemaError(null);
      })
      .catch((err) => {                                                       // Handle failures to load schema metadata.
        if (mounted) {
          setSchemaError((err as Error).message);
        }
      });
    return () => {                                                            // Cleanup to prevent setState after unmount.
      mounted = false;
    };
  }, []);

  useEffect(() => {
    try {
      let raw = localStorage.getItem(UI_STORAGE_KEY);
      if (!raw) raw = localStorage.getItem(UI_STORAGE_KEY_LEGACY);
      if (!raw) {
        setPersistReady(true);
        return;
      }
      const parsed = JSON.parse(raw) as PersistedUiV1 | PersistedUiV2;
      if (parsed.v === 1) {
        if (typeof parsed.question === "string") setQuestion(parsed.question);
        if (parsed.answer !== undefined) setAnswer(parsed.answer);
        if (parsed.agentLog !== undefined) setAgentLog(parsed.agentLog);
      } else if (parsed.v === 2) {
        if (typeof parsed.selectedPropertyId === "string") setSelectedPropertyId(parsed.selectedPropertyId);
        if (typeof parsed.startDate === "string") setStartDate(parsed.startDate);
        if (typeof parsed.endDate === "string") setEndDate(parsed.endDate);
        if (Array.isArray(parsed.reports)) setReports(parsed.reports);
        if (Array.isArray(parsed.selectedReportIds)) {
          const ids = new Set((parsed.reports ?? []).map((r) => r.id));
          const next = parsed.selectedReportIds.filter((id) => ids.has(id));
          setSelectedReportIds(
            next.length > 0 ? next : (parsed.reports ?? []).map((r) => r.id)
          );
        }
        if (Array.isArray(parsed.selectedDimensions)) setSelectedDimensions(parsed.selectedDimensions);
        if (Array.isArray(parsed.selectedMetrics)) setSelectedMetrics(parsed.selectedMetrics);
        if (typeof parsed.customReportName === "string") setCustomReportName(parsed.customReportName);
        if (typeof parsed.customReportGroup === "string") setCustomReportGroup(parsed.customReportGroup);
        if (typeof parsed.question === "string") setQuestion(parsed.question);
        if (parsed.answer !== undefined) setAnswer(parsed.answer);
        if (parsed.agentLog !== undefined) setAgentLog(parsed.agentLog);
      }
    } catch {
      /* ignore corrupt storage */
    }
    setPersistReady(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !persistReady) return;
    const snapshot = {
      selectedPropertyId,
      reports,
      question,
      answer,
      agentLog,
      selectedDimensions,
      selectedMetrics,
      customReportName,
      customReportGroup,
    };
    if (!hasSessionDataToPersist(snapshot)) {
      try {
        localStorage.removeItem(UI_STORAGE_KEY);
        localStorage.removeItem(UI_STORAGE_KEY_LEGACY);
      } catch {
        /* ignore */
      }
      return;
    }
    try {
      const reportIdSet = new Set(reports.map((r) => r.id));
      const selectedReportIdsSafe = selectedReportIds.filter((id) => reportIdSet.has(id));
      const payload: PersistedUiV2 = {
        v: 2,
        selectedPropertyId,
        startDate,
        endDate,
        reports,
        selectedReportIds: selectedReportIdsSafe,
        selectedDimensions,
        selectedMetrics,
        customReportName,
        customReportGroup,
        question,
        answer,
        agentLog,
        savedAt: Date.now(),
      };
      localStorage.setItem(UI_STORAGE_KEY, JSON.stringify(payload));
      try {
        localStorage.removeItem(UI_STORAGE_KEY_LEGACY);
      } catch {
        /* ignore */
      }
    } catch {
      setStatus("Could not save session in browser storage (data may be too large). Try clearing old data.");
    }
  }, [
    persistReady,
    selectedPropertyId,
    startDate,
    endDate,
    reports,
    selectedReportIds,
    selectedDimensions,
    selectedMetrics,
    customReportName,
    customReportGroup,
    question,
    answer,
    agentLog,
  ]);

  useEffect(() => {
    if (!persistReady || !connected || !selectedPropertyId.trim()) return;
    selectProperty(selectedPropertyId).catch(() => {
      /* property may be invalid or session expired */
    });
  }, [persistReady, connected, selectedPropertyId]);

  function handleClearSavedSession() {
    const { start, end } = defaultDateRange();
    setStartDate(start);
    setEndDate(end);
    setSelectedPropertyId("");
    setReports([]);
    setSelectedReportIds([]);
    setSelectedDimensions([]);
    setSelectedMetrics([]);
    setCustomReportName("");
    setCustomReportGroup("");
    setQuestion("");
    setAnswer(null);
    setAgentLog(null);
    setCustomReportError(null);
    setCustomReportSuccess(null);
    try {
      localStorage.removeItem(UI_STORAGE_KEY);
      localStorage.removeItem(UI_STORAGE_KEY_LEGACY);
    } catch {
      /* ignore */
    }
  }

  const showClearSavedSession =
    hasSessionDataToPersist({
      selectedPropertyId,
      reports,
      question,
      answer,
      agentLog,
      selectedDimensions,
      selectedMetrics,
      customReportName,
      customReportGroup,
    });

  /* -------------------------------------------------------------------------
   * Report loading and selection handlers
   * -------------------------------------------------------------------------
   */

  // Loads core reports for the selected property and date range.
  async function handleLoadReports() {
    if (!selectedPropertyId) {
      setStatus("Select a GA4 property before loading reports.");
      return;                                                                 // Exit when no property is selected.
    }
    setStatus("Loading reports...");
    try {
      await selectProperty(selectedPropertyId);                               // Persist property choice for backend calls.
      const result = await fetchCoreReports(startDate, endDate);              // Response payload containing core reports.
      setReports(result.reports);                                             // Store fetched reports for display.
      setSelectedReportIds(result.reports.map((report) => report.id));        // Default to all reports selected.
      setStatus(null);
    } catch (err) {                                                           // Handle API failures during report fetch.
      setStatus((err as Error).message);
    }
  }

  // Toggles a report's inclusion in the active selection list.
  function toggleReportSelection(reportId: string) {                          // reportId: report identifier to toggle.
    setSelectedReportIds((prev) =>
      prev.includes(reportId) ? prev.filter((id) => id !== reportId) : [...prev, reportId]
    );                                                                        // Add or remove the report id.
  }

  function selectAllReports() {
    setSelectedReportIds(reports.map((r) => r.id));
  }

  function unselectAllReports() {
    setSelectedReportIds([]);
  }

  const visibleReports = reports.filter((report) => selectedReportIds.includes(report.id));  // Reports active for tables/AI.
  const canAsk = visibleReports.length > 0 && question.trim().length > 0 && !isAsking;        // Eligibility for AI question.
  const canCreateCustomReport =
    selectedDimensions.length > 0 && selectedMetrics.length > 0 && !isCreatingReport;         // Eligibility for custom report creation.

  /* -------------------------------------------------------------------------
   * AI chat handlers
   * -------------------------------------------------------------------------
   */

  // Sends a free-form question to the AI using currently selected reports.
  async function handleAsk() {
    if (!canAsk) return;                                                      // Exit when input or state is invalid.
    setIsAsking(true);
    setAnswer(null);
    setAgentLog(null);
    try {
      const result = await runAnalysis({                                      // AI analysis response for the question.
        selected_reports: visibleReports,
        user_question: question.trim(),
        ...getAnalysisPromptExtras(null),
      });
      setAnswer(result.answer);                                               // Store the AI response for display.
      setAgentLog({
        request_id: result.request_id,
        agent_trace: result.agent_trace ?? [],
      });
    } catch (err) {                                                           // Handle AI request errors from backend.
      setAnswer((err as Error).message);
    } finally {
      setIsAsking(false);                                                     // Always clear the loading state.
    }
  }

  // Runs a predefined prompt template and displays the AI response.
  async function handleQuickPrompt(
    promptKey: string,                                                        // Backend template key to select a prompt.
    label: string                                                             // Button label used as the visible question.
  ) {
    if (visibleReports.length === 0 || isAsking) return;                      // Exit when no reports or busy.
    setIsAsking(true);
    setAnswer(null);
    setAgentLog(null);
    setQuestion(label);                                                       // Mirror the button label in the textbox.
    try {
      const result = await runAnalysis({                                      // AI analysis response for the template.
        selected_reports: visibleReports,
        user_question: label,
        prompt_key: promptKey,
        ...getAnalysisPromptExtras(promptKey),
      });
      setAnswer(result.answer);                                               // Store the AI response for display.
      setAgentLog({
        request_id: result.request_id,
        agent_trace: result.agent_trace ?? [],
      });
    } catch (err) {                                                           // Handle AI request errors from backend.
      setAnswer((err as Error).message);
    } finally {
      setIsAsking(false);                                                     // Always clear the loading state.
    }
  }

  // Creates a custom report using selected dimensions/metrics and appends it to the list.
  async function handleCreateCustomReport() {
    setCustomReportError(null);
    setCustomReportSuccess(null);
    if (!selectedDimensions.length || !selectedMetrics.length) {
      setCustomReportError("Select at least one dimension and one metric.");
      return;                                                                 // Exit when required selections are missing.
    }
    setIsCreatingReport(true);
    try {
      const result = await createCustomReport({
        start_date: startDate,
        end_date: endDate,
        metrics: selectedMetrics,
        dimensions: selectedDimensions,
      });
      const existingCustomCount = reports.filter((report) => report.id.startsWith("user_")).length;
      const reportIndex = existingCustomCount + 1;
      const displayName = customReportName.trim()
        ? customReportName.trim()
        : `Custom Report ${reportIndex}`;
      const groupName = customReportGroup.trim();
      const descriptionParts = [
        `Dimensions: ${selectedDimensions.join(", ")}`,
        `Metrics: ${selectedMetrics.join(", ")}`,
      ];
      if (groupName) {
        descriptionParts.push(`Group: ${groupName}`);
      }
      const newReport: ReportPayload = {
        id: `user_${reportIndex}`,
        name: displayName,
        description: descriptionParts.join(" | "),
        data: result.data,
      };
      setReports((prev) => [...prev, newReport]);
      setSelectedReportIds((prev) => [...prev, newReport.id]);
      setCustomReportSuccess("Custom report created.");
    } catch (err) {                                                           // Handle invalid combinations or API errors.
      setCustomReportError(
        "The selected metrics and dimensions are not compatible. Please try a different combination."
      );
    } finally {
      setIsCreatingReport(false);
    }
  }

  // Updates the multi-select state based on the current option list.
  function handleMultiSelectChange(
    event: React.ChangeEvent<HTMLSelectElement>,                              // HTML multi-select change event.
    setValues: (values: string[]) => void                                     // State updater for selected values.
  ) {
    const values = Array.from(event.target.selectedOptions).map((option) => option.value);
    setValues(values);                                                        // Persist selected option values.
  }

  // Formats a schema option into a readable label for the select list.
  function formatSchemaOption(item: ReportSchemaItem) {
    return `${item.label} - ${item.description} (${item.id})`;                // Return combined label for display.
  }

  async function handleLinkBigQueryExport() {
    setBqLinkMessage(null);
    if (!selectedPropertyId.trim()) {
      setBqLinkMessage("Select a GA4 property first.");
      return;
    }
    setBqLinkLoading(true);
    try {
      const result = await linkBigQueryExport({ streaming_export: bqStreaming });
      setBqLinkMessage(
        `${result.message} Grant: ${result.grant.status}. Link: ${result.bigquery_link.status}.`
      );
    } catch (err) {
      setBqLinkMessage((err as Error).message || "BigQuery link failed.");
    } finally {
      setBqLinkLoading(false);
    }
  }

  return (                                                                   // Render the main dashboard layout.
    <main>
      <h1>GA4 AI Analytics Platform</h1>
      <p>Connect GA4, pick a property, and load core report tables.</p>

      <section>
        <h2>Connect Google Analytics</h2>
        {!connected ? (
          <button onClick={() => (window.location.href = `${apiBase}/api/auth/login`)}>
            Connect GA4
          </button>
        ) : (
          <div className="stack">
            <div className="row">
              <span className="chip">Connected</span>
              <button onClick={() => (window.location.href = `${apiBase}/api/auth/login`)}>
                Reconnect
              </button>
            </div>
            <label>
              Property
              <select
                value={selectedPropertyId}
                onChange={(event) => setSelectedPropertyId(event.target.value)}
              >
                <option value="">Select a property</option>
                {properties.map((property) => (
                  <option key={property.property_id} value={property.property_id}>
                    {property.display_name} ({property.property_id})
                  </option>
                ))}
              </select>
            </label>
            <div className="stack">
              <label className="row">
                <input
                  type="checkbox"
                  checked={bqStreaming}
                  onChange={(e) => setBqStreaming(e.target.checked)}
                />
                Enable streaming export (optional; may increase cost)
              </label>
              <button
                type="button"
                onClick={handleLinkBigQueryExport}
                disabled={bqLinkLoading || !selectedPropertyId.trim()}
              >
                {bqLinkLoading ? "Linking BigQuery…" : "Link GA4 export to our BigQuery"}
              </button>
              {bqLinkMessage && <p className="form-success">{bqLinkMessage}</p>}
            </div>
          </div>
        )}
      </section>

      <section>
        <h2>Date range</h2>
        <label>
          Start
          <input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
        </label>
        <label>
          End
          <input
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </label>
        <button onClick={handleLoadReports}>Load reports</button>
      </section>

      <section>
        <h2>Custom report builder</h2>
        {!reportSchema ? (
          <p>{schemaError ?? "Loading report fields..."}</p>
        ) : (
          <div className="custom-report-builder">
            <label className="custom-report-field">
              Dimensions
              <select
                multiple
                value={selectedDimensions}
                onChange={(event) => handleMultiSelectChange(event, setSelectedDimensions)}
              >
                {reportSchema.dimensions.map((dimension) => (
                  <option key={dimension.id} value={dimension.id}>
                    {formatSchemaOption(dimension)}
                  </option>
                ))}
              </select>
            </label>
            <label className="custom-report-field">
              Metrics
              <select
                multiple
                value={selectedMetrics}
                onChange={(event) => handleMultiSelectChange(event, setSelectedMetrics)}
              >
                {reportSchema.metrics.map((metric) => (
                  <option key={metric.id} value={metric.id}>
                    {formatSchemaOption(metric)}
                  </option>
                ))}
              </select>
            </label>
            <label className="custom-report-field">
              Report name (optional)
              <input
                type="text"
                value={customReportName}
                onChange={(event) => setCustomReportName(event.target.value)}
                placeholder="Custom Report"
              />
            </label>
            <label className="custom-report-field">
              Report group (optional)
              <input
                type="text"
                value={customReportGroup}
                onChange={(event) => setCustomReportGroup(event.target.value)}
                placeholder="Group name"
              />
            </label>
            <div className="custom-report-actions">
              <button
                type="button"
                onClick={handleCreateCustomReport}
                disabled={!canCreateCustomReport}
              >
                {isCreatingReport ? "Creating..." : "Create report"}
              </button>
            </div>
            {customReportError && <p className="form-error">{customReportError}</p>}
            {customReportSuccess && <p className="form-success">{customReportSuccess}</p>}
          </div>
        )}
      </section>

      <section>
        <div className="report-select-toolbar">
          <h2>Active reports</h2>
          {reports.length > 0 && (
            <div className="report-select-actions">
              <button type="button" onClick={selectAllReports}>
                Select all
              </button>
              <button type="button" onClick={unselectAllReports}>
                Unselect all
              </button>
            </div>
          )}
        </div>
        {reports.length === 0 ? (
          <p>Load reports to choose which ones appear in tables and AI analysis.</p>
        ) : (
          <div className="report-select-list">
            {reports.map((report) => (
              <label key={report.id} className="report-select-item">
                <input
                  type="checkbox"
                  checked={selectedReportIds.includes(report.id)}
                  onChange={() => toggleReportSelection(report.id)}
                />
                <span className="report-select-name">{report.name}</span>
                <span className="report-select-desc">{report.description}</span>
              </label>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Report tables</h2>
        {reports.length > 0 && visibleReports.length === 0 ? (
          <p>Select at least one report to show tables.</p>
        ) : (
          <ReportsContainer reports={visibleReports} />
        )}
      </section>

      <AiPromptSettings />

      <section>
        <h2>Ask AI</h2>
        {reports.length === 0 ? (
          <p>Load reports to ask questions about them.</p>
        ) : visibleReports.length === 0 ? (
          <p>Select at least one report to ask questions.</p>
        ) : (
          <div className="chat-panel">
            <div className="prompt-buttons">
              {promptButtons.map((prompt) => (
                <button
                  key={prompt.key}
                  type="button"
                  className="prompt-button"
                  onClick={() => handleQuickPrompt(prompt.key, prompt.label)}
                  disabled={visibleReports.length === 0 || isAsking}
                >
                  {prompt.label}
                </button>
              ))}
            </div>
            <label className="chat-input">
              Question
              <textarea
                rows={4}
                placeholder="Ask about trends, anomalies, or comparisons..."
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
            </label>
            <div className="chat-actions">
              <button type="button" onClick={handleAsk} disabled={!canAsk}>
                {isAsking ? "Asking..." : "Ask AI"}
              </button>
              {showClearSavedSession && (
                <button type="button" className="chat-actions-secondary" onClick={handleClearSavedSession}>
                  Clear saved session
                </button>
              )}
            </div>
            {answer && (
              <AnswerRenderer
                answer={answer}
                selectedReports={visibleReports}
                agentLog={agentLog}
                onAgentLog={setAgentLog}
              />
            )}
          </div>
        )}
      </section>

      {status && <p>{status}</p>}
    </main>
  );
}

/* =============================================================================
 * Report Tables: tabbed container and fullscreen management
 * =============================================================================
 */

// Displays report tabs and the active report table panel.
function ReportsContainer({ reports }: { reports: ReportPayload[] }) {        // reports: report list for tabs and tables.
  /* -------------------------------------------------------------------------
   * Local UI state for report navigation and fullscreen mode
   * -------------------------------------------------------------------------
   */
  const [activeReportId, setActiveReportId] = useState<string | null>(null);  // Current report id being displayed.
  const [isFullscreen, setIsFullscreen] = useState(false);                    // Whether the report panel is fullscreen.

  /* -------------------------------------------------------------------------
   * Active report synchronization
   * -------------------------------------------------------------------------
   */
  useEffect(() => {
    if (reports.length === 0) {
      setActiveReportId(null);                                                // Clear active tab when no reports exist.
      return;                                                                 // Exit when there is nothing to select.
    }
    if (!activeReportId || !reports.some((report) => report.id === activeReportId)) {
      setActiveReportId(reports[0].id);                                       // Default to the first available report.
    }
  }, [reports, activeReportId]);

  /* -------------------------------------------------------------------------
   * Fullscreen keyboard and body-scroll management
   * -------------------------------------------------------------------------
   */
  useEffect(() => {
    if (!isFullscreen) return;                                                // Skip listeners when not fullscreen.
    const handleKeyDown = (event: KeyboardEvent) => {                         // ESC handler for exiting fullscreen.
      if (event.key === "Escape") {
        setIsFullscreen(false);                                               // Allow users to exit fullscreen with ESC.
      }
    };
    const previousOverflow = document.body.style.overflow;                    // Preserve existing scroll behavior.
    document.body.style.overflow = "hidden";                                  // Lock background scroll in fullscreen.
    window.addEventListener("keydown", handleKeyDown);
    return () => {                                                            // Cleanup listeners and restore scrolling.
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [isFullscreen]);

  if (reports.length === 0) {
    return <p>No reports loaded yet.</p>;                                      // Render empty state without tabs.
  }

  const activeReport = reports.find((report) => report.id === activeReportId) ?? reports[0]; // Report shown in panel.
  const canExport = Boolean(activeReport?.data?.length);                      // Enable CSV export only with data.

  // Exports the currently active report as a CSV file.
  const handleExportActiveReport = () => {
    if (!activeReportId || !activeReport?.data || activeReport.data.length === 0) {
      return;                                                                 // Exit when there is no data to export.
    }
    const projectName = "ga4-ai-dashboard";                                   // Project name used in export filename.
    const safeProjectName = sanitizeFilenamePart(projectName);                // Sanitized project name for filenames.
    const safeReportName = sanitizeFilenamePart(activeReport.name);           // Sanitized report name for filenames.
    const dateStamp = new Date().toISOString().slice(0, 10);                  // ISO date used in export filename.
    exportToCSV(
      activeReport.data,
      `${safeProjectName}_${safeReportName}_${dateStamp}.csv`
    );
  };

  const reportPanel = (                                                       // Reusable panel rendered in normal/fullscreen.
    <ReportPanel
      report={activeReport}
      onExpand={isFullscreen ? undefined : () => setIsFullscreen(true)}
      onClose={isFullscreen ? () => setIsFullscreen(false) : undefined}
      onExport={handleExportActiveReport}
      canExport={canExport}
      isFullscreen={isFullscreen}
    />
  );

  return (                                                                   // Render tabs and the active report panel.
    <div className="report-container">
      <div className="report-tabs">
        {reports.map((report) => (
          <button
            key={report.id}
            type="button"
            className={report.id === activeReport.id ? "report-tab active" : "report-tab"}
            onClick={() => setActiveReportId(report.id)}
          >
            {report.name}
          </button>
        ))}
      </div>
      {isFullscreen ? (
        <div className="report-overlay" role="dialog" aria-modal="true">
          <div className="report-modal">{reportPanel}</div>
        </div>
      ) : (
        reportPanel
      )}
    </div>
  );
}

/* =============================================================================
 * Formatting helpers for dates and filenames
 * =============================================================================
 */

// Sanitizes a string so it can be safely used in filenames.
function sanitizeFilenamePart(value: string) {                                // value: raw label to be used in filenames.
  return value                                                                // Return a filename-safe version of the text.
    .trim()
    .replace(/\s+/g, "_")
    .replace(/[^a-zA-Z0-9_-]/g, "");
}

/* =============================================================================
 * Report Panel: table rendering and action buttons
 * =============================================================================
 */

type ReportPanelProps = {
  report: ReportPayload;                                                      // Report payload to render in the panel.
  onExpand?: () => void;                                                      // Callback for entering fullscreen view.
  onClose?: () => void;                                                       // Callback for closing fullscreen view.
  onExport?: () => void;                                                      // Callback for exporting the report data.
  canExport?: boolean;                                                        // Whether export action is enabled.
  isFullscreen?: boolean;                                                     // Whether the panel is in fullscreen mode.
};

type SortDirection = "asc" | "desc";

const parseMaybeNumber = (value: unknown) => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const fromAnswer = parseAnswerNumber(value);
    if (fromAnswer !== null) {
      return fromAnswer;
    }
    const normalized = value.replace(/,/g, "").trim();
    if (!normalized) {
      return null;
    }
    const parsed = Number(normalized);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
};

/** Column header or metric name hints that values may mix 0–1 fractions with 1–100 percent points. */
function isLikelyPercentSortColumn(columnKey: string | undefined) {
  if (!columnKey) return false;
  const lower = columnKey.toLowerCase();
  if (lower.includes("%")) return true;
  return (
    /\b(percent|percentage|bounce|conversion|ctr|proportion|ratio|share)\b/i.test(columnKey) ||
    /\b(bounce|exit|conversion|engagement|click|churn)\s+rate\b/i.test(lower)
  );
}

/**
 * Aligns mixed percentage scales for sorting: e.g. 0.97 (97% as fraction) vs 1.56 (1.56% as points).
 * Without this, 1.56 sorts above 0.97 numerically.
 */
function normalizePercentPairForSort(a: number, b: number): [number, number] {
  const aUnit = a >= 0 && a <= 1;
  const bUnit = b >= 0 && b <= 1;
  if (aUnit && bUnit) return [a * 100, b * 100];
  if (aUnit && !bUnit) return [a * 100, b];
  if (!aUnit && bUnit) return [a, b * 100];
  return [a, b];
}

function shouldNormalizePercentPair(
  aRaw: string,
  bRaw: string,
  columnKey: string | undefined
): boolean {
  if (isLikelyPercentSortColumn(columnKey)) return true;
  if (aRaw.includes("%") || bRaw.includes("%")) return true;
  return false;
}

/** Same signals as pair-normalize, for a single cell (bar width / column max). */
function shouldNormalizePercentBar(raw: string, columnHeader: string): boolean {
  return isLikelyPercentSortColumn(columnHeader) || raw.includes("%");
}

/**
 * Maps parsed numbers to a 0–100 style scale for bar length when the column mixes
 * decimal fractions (0.97 = 97%) with percent points (1.56 = 1.56%).
 */
function normalizeParsedForPercentBar(
  parsed: number,
  raw: string,
  columnHeader: string
): number {
  if (!shouldNormalizePercentBar(raw, columnHeader)) return parsed;
  if (parsed >= 0 && parsed <= 1) return parsed * 100;
  return parsed;
}

const compareValues = (a: unknown, b: unknown, columnKey?: string) => {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;

  const aStr = String(a);
  const bStr = String(b);
  const aNum = parseMaybeNumber(a);
  const bNum = parseMaybeNumber(b);
  if (aNum != null && bNum != null) {
    if (shouldNormalizePercentPair(aStr, bStr, columnKey)) {
      const [an, bn] = normalizePercentPairForSort(aNum, bNum);
      return an - bn;
    }
    return aNum - bNum;
  }

  return aStr.localeCompare(bStr, undefined, {
    numeric: true,
    sensitivity: "base",
  });
};

// Renders a single report panel with actions and a data table.
function ReportPanel({
  report,                                                                     // Report payload providing labels and data.
  onExpand,                                                                   // Handler to open fullscreen mode.
  onClose,                                                                    // Handler to close fullscreen mode.
  onExport,                                                                   // Handler to export CSV data.
  canExport,                                                                  // Flag for enabling/disabling export.
  isFullscreen,                                                               // Flag indicating fullscreen layout.
}: ReportPanelProps) {
  const rows = report.data;                                                   // Data rows for the report table.
  const columns = rows.length ? Object.keys(rows[0]) : [];                    // Column labels derived from row keys.
  const [sortConfig, setSortConfig] = useState<{
    key: string;
    direction: SortDirection;
  } | null>(null);

  const sortedRows = useMemo(() => {
    if (!sortConfig) return rows;
    const multiplier = sortConfig.direction === "asc" ? 1 : -1;
    const rowsWithIndex = rows.map((row, index) => ({ row, index }));
    rowsWithIndex.sort((left, right) => {
      const order = compareValues(left.row[sortConfig.key], right.row[sortConfig.key], sortConfig.key);
      if (order !== 0) {
        return order * multiplier;
      }
      return left.index - right.index;
    });
    return rowsWithIndex.map((item) => item.row);
  }, [rows, sortConfig]);

  const handleSort = (column: string) => {
    setSortConfig((prev) => {
      if (prev?.key === column) {
        return {
          key: column,
          direction: prev.direction === "asc" ? "desc" : "asc",
        };
      }
      return { key: column, direction: "asc" };
    });
  };

  return (                                                                   // Render the report card UI and table.
    <div className={isFullscreen ? "report-block report-block-fullscreen" : "report-block"}>
      <div className="report-title">
        <div className="report-title-row">
          <strong>{report.name}</strong>
          <div className="report-actions">
            <button
              type="button"
              className="report-action-icon"
              onClick={onExport}
              disabled={!canExport}
              aria-label="Download report as CSV"
              title="Download CSV"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 3a1 1 0 0 1 1 1v8.59l2.3-2.3a1 1 0 1 1 1.4 1.42l-4.01 4.01a1 1 0 0 1-1.4 0l-4.01-4.01a1 1 0 1 1 1.4-1.42l2.31 2.3V4a1 1 0 0 1 1-1Zm-6 14a1 1 0 0 1 1 1v1h10v-1a1 1 0 1 1 2 0v2a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1Z" />
              </svg>
            </button>
            {onExpand ? (
              <button
                type="button"
                className="report-action-icon"
                onClick={onExpand}
                aria-label="Expand report"
                title="Expand"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 9a1 1 0 0 1 1-1h3a1 1 0 1 1 0 2H6v2a1 1 0 1 1-2 0V9Zm10-1a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v4a1 1 0 1 1-2 0v-3h-3a1 1 0 0 1-1-1Zm-8 7a1 1 0 0 1 1 1v3h3a1 1 0 1 1 0 2H6a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1Zm12 0a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1h-4a1 1 0 1 1 0-2h3v-3a1 1 0 0 1 1-1Z" />
                </svg>
              </button>
            ) : null}
            {onClose ? (
              <button type="button" className="report-action-button" onClick={onClose}>
                Close
              </button>
            ) : null}
          </div>
        </div>
        <span>{report.description}</span>
      </div>
      {rows.length === 0 ? (
        <p>No rows returned.</p>
      ) : (
        <div className="report-table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                {columns.map((col) => {
                  const isSorted = sortConfig?.key === col;
                  const direction = isSorted ? sortConfig?.direction : null;
                  const indicator = direction === "asc" ? "^" : direction === "desc" ? "v" : "";
                  return (
                    <th key={col} aria-sort={direction ? (direction === "asc" ? "ascending" : "descending") : "none"}>
                      <button
                        type="button"
                        className="report-sort-button"
                        onClick={() => handleSort(col)}
                      >
                        <span className="report-sort-label">{col}</span>
                        <span className="report-sort-indicator">{indicator}</span>
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row, idx) => (
                <tr key={`${report.id}-${idx}`}>
                  {columns.map((col) => (
                    <td key={`${report.id}-${idx}-${col}`}>
                      {String(row[col] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

type AnswerBlock =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; headers: string[]; rows: string[][] };

type InsightFollowupAction = "basis" | "deep_dive";

type InsightFollowupState = {
  loading?: InsightFollowupAction | null;
  basis?: string;
  deepDive?: string;
  error?: string | null;
};

function parseTableRow(line: string) {
  const trimmed = line.trim();
  const normalized = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const withoutEdge = normalized.endsWith("|") ? normalized.slice(0, -1) : normalized;
  return withoutEdge.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string) {
  return /^\s*\|?[-:\s|]+\|?\s*$/.test(line);
}

function isBulletLine(line: string) {
  return /^[-*]\s+/.test(line) || line.startsWith("•");
}

function cleanAnswerText(value: string) {
  return value
    .replace(/^\*{1,3}\s*/, "")
    .replace(/\s*\*{1,3}$/, "")
    .trim();
}

function parseAnswerBlocks(answer: string): AnswerBlock[] {
  const lines = answer.split(/\r?\n/);
  const blocks: AnswerBlock[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      i += 1;
      continue;
    }

    if (/^[-*]{3,}$/.test(trimmed)) {
      i += 1;
      continue;
    }

    if (trimmed.startsWith("##")) {
      blocks.push({
        type: "heading",
        text: cleanAnswerText(trimmed.replace(/^#+\s*/, "")),
      });
      i += 1;
      continue;
    }

    const next = lines[i + 1]?.trim() ?? "";
    if (trimmed.includes("|") && isTableSeparator(next)) {
      const headers = parseTableRow(trimmed);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim()) {
        rows.push(parseTableRow(lines[i]));
        i += 1;
      }
      blocks.push({ type: "table", headers, rows });
      continue;
    }

    if (isBulletLine(trimmed)) {
      const items: string[] = [];
      while (i < lines.length) {
        const itemLine = lines[i].trim();
        if (!isBulletLine(itemLine)) break;
        const parts = itemLine
          .split(/\s+[-*]\s+|\s+•\s+|•/)
          .map((part) => cleanAnswerText(part.replace(/^[-*•]\s*/, "")))
          .filter(Boolean);
        items.push(...parts);
        i += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }

    if (trimmed.includes("•")) {
      const items = trimmed
        .split(/\s+•\s+|•/)
        .map((part) => cleanAnswerText(part.replace(/^[-*•]\s*/, "")))
        .filter(Boolean);
      if (items.length > 1) {
        blocks.push({ type: "list", items });
        i += 1;
        continue;
      }
    }

    const paragraphLines: string[] = [];
    while (i < lines.length) {
      const paraLine = lines[i].trim();
      if (!paraLine) break;
      if (/^[-*]{3,}$/.test(paraLine)) break;
      if (paraLine.startsWith("##")) break;
      const lookahead = lines[i + 1]?.trim() ?? "";
      if (paraLine.includes("|") && isTableSeparator(lookahead)) break;
      if (isBulletLine(paraLine)) break;
      paragraphLines.push(cleanAnswerText(paraLine));
      i += 1;
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

function AgentLogToolbar({
  agentLog,
}: {
  agentLog: { request_id: string; agent_trace: AgentTraceEvent[] };
}) {
  const [open, setOpen] = useState(false);
  function download() {
    const blob = new Blob(
      [
        JSON.stringify(
          { request_id: agentLog.request_id, agent_trace: agentLog.agent_trace },
          null,
          2
        ),
      ],
      { type: "application/json;charset=utf-8" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `agent-trace-${agentLog.request_id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="agent-log-toolbar">
      <span className="agent-log-meta" title={agentLog.request_id}>
        Agent run <code>{agentLog.request_id.slice(0, 8)}</code>…
      </span>
      <button type="button" className="agent-log-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "Hide log" : "View log"}
      </button>
      <button type="button" className="agent-log-download" onClick={download}>
        Download JSON
      </button>
      {open && (
        <pre className="agent-log-pre">
          {agentLog.agent_trace.length > 0
            ? JSON.stringify(agentLog.agent_trace, null, 2)
            : "(No structured events; enable include_agent_trace or check server logs.)"}
        </pre>
      )}
    </div>
  );
}

function AnswerRenderer({
  answer,
  selectedReports,
  agentLog,
  onAgentLog,
}: {
  answer: string;
  selectedReports: ReportPayload[];
  agentLog: { request_id: string; agent_trace: AgentTraceEvent[] } | null;
  onAgentLog: (log: { request_id: string; agent_trace: AgentTraceEvent[] }) => void;
}) {
  const blocks = useMemo(() => parseAnswerBlocks(answer), [answer]);
  const [insightFollowups, setInsightFollowups] = useState<Record<string, InsightFollowupState>>({});

  useEffect(() => {
    setInsightFollowups({});
  }, [answer]);

  async function handleInsightFollowup(
    insightId: string,
    insightText: string,
    action: InsightFollowupAction
  ) {
    setInsightFollowups((prev) => ({
      ...prev,
      [insightId]: {
        ...(prev[insightId] ?? {}),
        loading: action,
        error: null,
      },
    }));

    try {
      const promptKey =
        action === "basis"
          ? "insight_basis_explainer"
          : "insight_deep_dive_recommendations";
      const result = await runAnalysis({
        selected_reports: selectedReports,
        user_question: insightText,
        prompt_key: promptKey,
        ...getAnalysisPromptExtras(promptKey),
      });
      onAgentLog({
        request_id: result.request_id,
        agent_trace: result.agent_trace ?? [],
      });
      setInsightFollowups((prev) => ({
        ...prev,
        [insightId]: {
          ...(prev[insightId] ?? {}),
          loading: null,
          error: null,
          basis: action === "basis" ? result.answer : prev[insightId]?.basis,
          deepDive: action === "deep_dive" ? result.answer : prev[insightId]?.deepDive,
        },
      }));
    } catch (err) {
      setInsightFollowups((prev) => ({
        ...prev,
        [insightId]: {
          ...(prev[insightId] ?? {}),
          loading: null,
          error: (err as Error).message,
        },
      }));
    }
  }

  let activeSection = "";
  return (
    <div className="answer">
      {agentLog && <AgentLogToolbar agentLog={agentLog} />}
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          activeSection = block.text.trim().toLowerCase();
          return (
            <h3 key={`answer-heading-${index}`} className="answer-heading">
              {block.text}
            </h3>
          );
        }
        if (block.type === "table") {
          return <AnswerTable key={`answer-table-${index}`} block={block} />;
        }
        if (block.type === "list") {
          const isInsightsSection = activeSection === "insights";
          return (
            <ul key={`answer-list-${index}`} className="answer-list">
              {block.items.map((item, itemIdx) => (
                <li key={`answer-item-${index}-${itemIdx}`}>
                  {isInsightsSection ? (
                    <div className="insight-item">
                      <span>{item}</span>
                      <div className="insight-actions">
                        <button
                          type="button"
                          className="insight-action-button"
                          onClick={() =>
                            handleInsightFollowup(`${index}-${itemIdx}`, item, "basis")
                          }
                          disabled={insightFollowups[`${index}-${itemIdx}`]?.loading != null}
                        >
                          {insightFollowups[`${index}-${itemIdx}`]?.loading === "basis"
                            ? "Loading basis..."
                            : "What is this based on?"}
                        </button>
                        <button
                          type="button"
                          className="insight-action-button"
                          onClick={() =>
                            handleInsightFollowup(`${index}-${itemIdx}`, item, "deep_dive")
                          }
                          disabled={insightFollowups[`${index}-${itemIdx}`]?.loading != null}
                        >
                          {insightFollowups[`${index}-${itemIdx}`]?.loading === "deep_dive"
                            ? "Loading deep dive..."
                            : "Deep dive recommendations"}
                        </button>
                      </div>
                      {insightFollowups[`${index}-${itemIdx}`]?.error && (
                        <p className="insight-followup-error">
                          {insightFollowups[`${index}-${itemIdx}`]?.error}
                        </p>
                      )}
                      {insightFollowups[`${index}-${itemIdx}`]?.basis && (
                        <div className="insight-followup">
                          <strong>What this is based on</strong>
                          <ReadOnlyAnswerRenderer
                            answer={insightFollowups[`${index}-${itemIdx}`]?.basis ?? ""}
                          />
                        </div>
                      )}
                      {insightFollowups[`${index}-${itemIdx}`]?.deepDive && (
                        <div className="insight-followup">
                          <strong>Deep dive recommendations</strong>
                          <ReadOnlyAnswerRenderer
                            answer={insightFollowups[`${index}-${itemIdx}`]?.deepDive ?? ""}
                          />
                        </div>
                      )}
                    </div>
                  ) : (
                    item
                  )}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={`answer-paragraph-${index}`} className="answer-paragraph">
            {block.text}
          </p>
        );
      })}
    </div>
  );
}

function ReadOnlyAnswerRenderer({ answer }: { answer: string }) {
  const blocks = useMemo(() => parseAnswerBlocks(answer), [answer]);
  return (
    <div className="answer answer-followup">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return (
            <h3 key={`followup-heading-${index}`} className="answer-heading">
              {block.text}
            </h3>
          );
        }
        if (block.type === "table") {
          return <AnswerTable key={`followup-table-${index}`} block={block} />;
        }
        if (block.type === "list") {
          return (
            <ul key={`followup-list-${index}`} className="answer-list">
              {block.items.map((item, itemIdx) => (
                <li key={`followup-item-${index}-${itemIdx}`}>{item}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={`followup-paragraph-${index}`} className="answer-paragraph">
            {block.text}
          </p>
        );
      })}
    </div>
  );
}

function AnswerTable({
  block,
}: {
  block: Extract<AnswerBlock, { type: "table" }>;
}) {
  const [sortConfig, setSortConfig] = useState<{
    colIdx: number;
    direction: SortDirection;
  } | null>(null);

  const sortedRows = useMemo(() => {
    if (!sortConfig) return block.rows;
    const multiplier = sortConfig.direction === "asc" ? 1 : -1;
    const rowsWithIndex = block.rows.map((row, index) => ({ row, index }));
    rowsWithIndex.sort((left, right) => {
      const leftValue = String(left.row[sortConfig.colIdx] ?? "");
      const rightValue = String(right.row[sortConfig.colIdx] ?? "");
      const header = block.headers[sortConfig.colIdx] ?? "";
      const order = compareAnswerCellValues(leftValue, rightValue, header);
      if (order !== 0) {
        return order * multiplier;
      }
      return left.index - right.index;
    });
    return rowsWithIndex.map((item) => item.row);
  }, [block.rows, sortConfig]);

  const columnMaxes = useMemo(
    () =>
      block.headers.map((header, colIdx) => {
        let max = 0;
        block.rows.forEach((row) => {
          const raw = String(row[colIdx] ?? "");
          const value = parseAnswerNumber(raw);
          if (value === null) return;
          const scaled = normalizeParsedForPercentBar(value, raw, header);
          if (scaled > max) max = scaled;
        });
        return max;
      }),
    [block.headers, block.rows]
  );

  const handleSort = (colIdx: number) => {
    setSortConfig((prev) => {
      if (prev?.colIdx === colIdx) {
        return {
          colIdx,
          direction: prev.direction === "asc" ? "desc" : "asc",
        };
      }
      return { colIdx, direction: "asc" };
    });
  };

  return (
    <div className="answer-table-wrap">
      <table className="answer-table">
        <thead>
          <tr>
            {block.headers.map((header, colIdx) => {
              const isSorted = sortConfig?.colIdx === colIdx;
              const direction = isSorted ? sortConfig?.direction : null;
              const indicator = direction === "asc" ? "^" : direction === "desc" ? "v" : "";
              return (
                <th
                  key={`answer-head-${colIdx}`}
                  aria-sort={direction ? (direction === "asc" ? "ascending" : "descending") : "none"}
                >
                  <button
                    type="button"
                    className="report-sort-button"
                    onClick={() => handleSort(colIdx)}
                  >
                    <span className="report-sort-label">{header}</span>
                    <span className="report-sort-indicator">{indicator}</span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, rowIdx) => (
            <tr key={`answer-row-${rowIdx}`}>
              {block.headers.map((header, cellIdx) => (
                <AnswerCell
                  key={`answer-cell-${rowIdx}-${cellIdx}`}
                  value={row[cellIdx] ?? ""}
                  columnName={header}
                  maxValue={columnMaxes[cellIdx]}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function parseAnswerNumber(raw: string) {
  if (!raw) return null;
  const duration = parseDurationToSeconds(raw);
  if (duration !== null) {
    return duration;
  }
  const trimmed = raw.trim();
  const secondsSuffix = trimmed.match(/^([\d,.]+)\s*(s|sec|secs|second|seconds)\s*$/i);
  if (secondsSuffix) {
    const n = Number(secondsSuffix[1].replace(/,/g, ""));
    if (Number.isFinite(n)) return n;
  }
  const normalized = raw
    .replace(/[%,$]/g, "")
    .replace(/\s+/g, "")
    .replace(/,/g, "");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Parses clock-like durations for answer tables.
 * - H:MM:SS — hours, minutes, seconds (minutes/seconds 0–59)
 * - M:SS or MM:SS or 90:00 — total minutes : seconds (second part 0–59); common for engagement
 */
function parseDurationToSeconds(raw: string) {
  const trimmed = raw.trim();
  const three = trimmed.match(/^(\d+):(\d{2}):(\d{2})$/);
  if (three) {
    const h = Number(three[1]);
    const m = Number(three[2]);
    const s = Number(three[3]);
    if ([h, m, s].some((v) => Number.isNaN(v)) || m > 59 || s > 59) return null;
    return h * 3600 + m * 60 + s;
  }
  const two = trimmed.match(/^(\d+):(\d{2})$/);
  if (two) {
    const minutes = Number(two[1]);
    const seconds = Number(two[2]);
    if (Number.isNaN(minutes) || Number.isNaN(seconds) || seconds > 59) return null;
    return minutes * 60 + seconds;
  }
  return null;
}

/** Sort answer table cells using the same numeric rules as bars (%, duration, plain numbers). */
function compareAnswerCellValues(a: string, b: string, columnHeader?: string) {
  const an = parseAnswerNumber(a);
  const bn = parseAnswerNumber(b);
  if (an !== null && bn !== null) {
    if (shouldNormalizePercentPair(a, b, columnHeader)) {
      const [anN, bnN] = normalizePercentPairForSort(an, bn);
      return anN - bnN;
    }
    return an - bn;
  }
  if (an !== null && bn === null) return -1;
  if (an === null && bn !== null) return 1;
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

/**
 * Maps table header text to bar color family. Avoid matching substrings like "session" inside
 * "Session Source" / "Session Medium" — those are dimensions and would flip colors by property
 * depending on how the model labels columns.
 */
function columnKind(name: string) {
  const lower = name.toLowerCase();
  if (/session\s+(source|medium|campaign|channel|default|google)/i.test(name)) return "generic";
  if (lower.includes("revenue")) return "revenue";
  if (lower.includes("conversion") || /\bconv\.?\b/.test(lower)) return "conversion";
  if (lower.includes("bounce")) return "bounce";
  if (lower.includes("session length")) return "session-length";
  if (lower.includes("engagement") && lower.includes("duration")) return "session-length";
  if (lower.includes("duration") && lower.includes("per session")) return "session-length";
  if (lower.includes("user engagement")) return "session-length";
  if (lower.includes("engagement")) return "session-length";
  if (lower.includes("duration")) return "session-length";
  if (/\busers?\b/.test(lower) || lower.includes("new users") || lower.includes("total users")) return "users";
  if (/\bsessions?\b/.test(lower)) return "sessions";
  return "generic";
}

function formatPercentageValue(value: string, columnName: string): string {
  const lower = columnName.toLowerCase();
  const isRateColumn =
    lower.includes("bounce") ||
    lower.includes("conversion") ||
    /\bconv\.?\b/.test(lower) ||
    lower.includes("engagement");
  if (!isRateColumn) return value;
  
  const numericValue = parseAnswerNumber(value);
  if (numericValue === null) return value;
  
  // If value is between 0 and 1, it's a decimal (0.85) - convert to percentage (85%)
  // If value is between 1 and 100, it's already a percentage (85) - just add %
  // If value is > 100, it might already have % symbol or be formatted
  if (numericValue >= 0 && numericValue <= 1) {
    return `${(numericValue * 100).toFixed(2)}%`;
  } else if (numericValue > 1 && numericValue <= 100) {
    // Check if value already has % symbol
    if (value.includes("%")) return value;
    return `${numericValue.toFixed(2)}%`;
  }
  
  return value;
}

function AnswerCell({
  value,
  columnName,
  maxValue,
}: {
  value: string;
  columnName: string;
  maxValue: number;
}) {
  const numericValue = parseAnswerNumber(value);
  const barValue =
    numericValue === null
      ? null
      : normalizeParsedForPercentBar(numericValue, value, columnName);
  const ratio = maxValue > 0 && barValue !== null ? Math.min(barValue / maxValue, 1) : 0;
  const kind = columnKind(columnName);
  const showBar = numericValue !== null;
  const formattedValue = formatPercentageValue(value, columnName);
  
  return (
    <td className={showBar ? "answer-bar-cell" : undefined}>
      {showBar ? (
        <div className={`answer-bar answer-bar-${kind}`} style={{ ["--fill" as never]: ratio }}>
          <span>{formattedValue}</span>
        </div>
      ) : (
        formattedValue
      )}
    </td>
  );
}

