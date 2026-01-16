"use client";

import { useEffect, useState } from "react";
import {
  fetchAuthStatus,
  fetchCoreReports,
  fetchProperties,
  selectProperty,
  type ReportPayload,
} from "../lib/api";
import { exportToCSV } from "../lib/exportCsv";

export default function HomePage() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  const [startDate, setStartDate] = useState(() => {
    const today = new Date();
    const prior = new Date(today);
    prior.setDate(today.getDate() - 30);
    return formatDateInput(prior);
  });
  const [endDate, setEndDate] = useState(() => formatDateInput(new Date()));
  const [reports, setReports] = useState<ReportPayload[]>([]);
  const [connected, setConnected] = useState(false);
  const [properties, setProperties] = useState<
    { property_id: string; display_name: string }[]
  >([]);
  const [selectedPropertyId, setSelectedPropertyId] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchAuthStatus()
      .then((result) => {
        if (!mounted) return;
        setConnected(result.connected);
        if (result.connected) {
          return fetchProperties();
        }
        return null;
      })
      .then((result) => {
        if (!mounted || !result) return;
        setProperties(result.properties);
      })
      .catch((err) => {
        if (mounted) {
          setStatus((err as Error).message);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  async function handleLoadReports() {
    if (!selectedPropertyId) {
      setStatus("Select a GA4 property before loading reports.");
      return;
    }
    setStatus("Loading reports...");
    try {
      await selectProperty(selectedPropertyId);
      const result = await fetchCoreReports(startDate, endDate);
      setReports(result.reports);
      setStatus(null);
    } catch (err) {
      setStatus((err as Error).message);
    }
  }

  return (
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
        <h2>Report tables</h2>
        <ReportsContainer reports={reports} />
      </section>

      {status && <p>{status}</p>}
    </main>
  );
}

function ReportsContainer({ reports }: { reports: ReportPayload[] }) {
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (reports.length === 0) {
      setActiveReportId(null);
      return;
    }
    if (!activeReportId || !reports.some((report) => report.id === activeReportId)) {
      setActiveReportId(reports[0].id);
    }
  }, [reports, activeReportId]);

  useEffect(() => {
    if (!isFullscreen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsFullscreen(false);
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [isFullscreen]);

  if (reports.length === 0) {
    return <p>No reports loaded yet.</p>;
  }

  const activeReport = reports.find((report) => report.id === activeReportId) ?? reports[0];
  const canExport = Boolean(activeReport?.data?.length);
  const handleExportActiveReport = () => {
    if (!activeReportId || !activeReport?.data || activeReport.data.length === 0) {
      return;
    }
    const projectName = "ga4-ai-dashboard";
    const safeProjectName = sanitizeFilenamePart(projectName);
    const safeReportName = sanitizeFilenamePart(activeReport.name);
    const dateStamp = new Date().toISOString().slice(0, 10);
    exportToCSV(
      activeReport.data,
      `${safeProjectName}_${safeReportName}_${dateStamp}.csv`
    );
  };

  const reportPanel = (
    <ReportPanel
      report={activeReport}
      onExpand={isFullscreen ? undefined : () => setIsFullscreen(true)}
      onClose={isFullscreen ? () => setIsFullscreen(false) : undefined}
      onExport={handleExportActiveReport}
      canExport={canExport}
      isFullscreen={isFullscreen}
    />
  );

  return (
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

function formatDateInput(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function sanitizeFilenamePart(value: string) {
  return value
    .trim()
    .replace(/\s+/g, "_")
    .replace(/[^a-zA-Z0-9_-]/g, "");
}

type ReportPanelProps = {
  report: ReportPayload;
  onExpand?: () => void;
  onClose?: () => void;
  onExport?: () => void;
  canExport?: boolean;
  isFullscreen?: boolean;
};

function ReportPanel({
  report,
  onExpand,
  onClose,
  onExport,
  canExport,
  isFullscreen,
}: ReportPanelProps) {
  const rows = report.data;
  const columns = rows.length ? Object.keys(rows[0]) : [];

  return (
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
