"use client";

import { useEffect, useState } from "react";
import {
  fetchAuthStatus,
  fetchCoreReports,
  fetchProperties,
  selectProperty,
  type ReportPayload,
} from "../lib/api";

export default function HomePage() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-01-31");
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
        {reports.length === 0 ? (
          <p>No reports loaded yet.</p>
        ) : (
          <div className="stack">
            {reports.map((report) => {
              const rows = report.data.slice(0, 5);
              const columns = rows.length ? Object.keys(rows[0]) : [];
              return (
                <div key={report.id} className="report-block">
                  <div className="report-title">
                    <strong>{report.name}</strong>
                    <span>{report.description}</span>
                  </div>
                  {rows.length === 0 ? (
                    <p>No rows returned.</p>
                  ) : (
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
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {status && <p>{status}</p>}
    </main>
  );
}
