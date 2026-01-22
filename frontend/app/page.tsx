// This file defines the main GA4 AI dashboard page and its client-side logic. It manages
// report loading, report selection, and the AI Q&A interface that uses those reports.
"use client";

import { useEffect, useState } from "react";
import {
  fetchAuthStatus,
  fetchCoreReports,
  fetchProperties,
  fetchReportSchema,
  createCustomReport,
  selectProperty,
  runAnalysis,
  type ReportPayload,
  type ReportSchemaItem,
} from "../lib/api";
import { exportToCSV } from "../lib/exportCsv";

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
  const [startDate, setStartDate] = useState(() => {                          // Start date for report queries.
    const today = new Date();                                                 // Current date used for default range.
    const prior = new Date(today);                                            // Copy used to subtract days.
    prior.setDate(today.getDate() - 30);                                      // Default window starts 30 days ago.
    return formatDateInput(prior);                                            // Return ISO date string for input value.
  });
  const [endDate, setEndDate] = useState(() => formatDateInput(new Date()));   // End date for report queries.
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
    try {
      const result = await runAnalysis({                                      // AI analysis response for the question.
        selected_reports: visibleReports,
        user_question: question.trim(),
        coverage_pct: 90,
      });
      setAnswer(result.answer);                                               // Store the AI response for display.
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
    setQuestion(label);                                                       // Mirror the button label in the textbox.
    try {
      const result = await runAnalysis({                                      // AI analysis response for the template.
        selected_reports: visibleReports,
        user_question: label,
        prompt_key: promptKey,
        coverage_pct: 90,
      });
      setAnswer(result.answer);                                               // Store the AI response for display.
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
        <h2>Active reports</h2>
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
            </div>
            {answer && <div className="answer">{answer}</div>}
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

// Formats a Date object into an ISO string suitable for date inputs.
function formatDateInput(date: Date) {                                        // date: Date object to format for inputs.
  const year = date.getFullYear();                                            // Year component for the date string.
  const month = String(date.getMonth() + 1).padStart(2, "0");                 // Month component with leading zero.
  const day = String(date.getDate()).padStart(2, "0");                        // Day component with leading zero.
  return `${year}-${month}-${day}`;                                           // Return ISO date value for inputs.
}

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
                {columns.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
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
