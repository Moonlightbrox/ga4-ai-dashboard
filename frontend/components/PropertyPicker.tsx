"use client";

/**
 * PropertyPicker -- the only thing in the page that still talks to the
 * GA4 Admin API. Three jobs:
 *
 *   1. Show the user's auth state (Connect / Connected) and own the
 *      OAuth redirect to ``/api/auth/login``.
 *   2. Let the user pick which GA4 property is "current" for this
 *      session; persist that choice via :func:`selectProperty`.
 *   3. Trigger the one-click ``link GA4 export to BigQuery`` flow.
 *
 * The picker reports ``ready=true`` upward only after both auth and
 * property selection are settled, so the parent can gate the analyst
 * experience (Deep Scans + chat) until BigQuery is reachable.
 */

import { useEffect, useState } from "react";

import {
  fetchAuthStatus,
  fetchProperties,
  linkBigQueryExport,
  selectProperty,
  type Property,
} from "../lib/api";


export function PropertyPicker({
  onReadyChange,
}: {
  onReadyChange?: (ready: boolean, propertyId: string) => void;
}) {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

  const [connected, setConnected] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedPropertyId, setSelectedPropertyId] = useState("");
  const [propertyError, setPropertyError] = useState<string | null>(null);

  const [bqStreaming, setBqStreaming] = useState(false);
  const [bqLinkLoading, setBqLinkLoading] = useState(false);
  const [bqLinkMessage, setBqLinkMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAuthStatus()
      .then((s) => {
        if (cancelled) return;
        if (s.connected) {
          setConnected(true);
          return fetchProperties();
        }
        setConnected(false);
        return null;
      })
      .then((res) => {
        if (cancelled || !res) return;
        setProperties(res.properties);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setAuthError((err as Error).message || "Auth check failed.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedPropertyId.trim()) {
      onReadyChange?.(false, "");
      return;
    }
    let cancelled = false;
    selectProperty(selectedPropertyId)
      .then(() => {
        if (cancelled) return;
        setPropertyError(null);
        onReadyChange?.(true, selectedPropertyId);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setPropertyError(
          (err as Error).message ||
            "Could not select property. Try reconnecting Google."
        );
        onReadyChange?.(false, "");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPropertyId, onReadyChange]);

  async function handleLinkBigQuery() {
    setBqLinkMessage(null);
    if (!selectedPropertyId.trim()) {
      setBqLinkMessage("Select a property first.");
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

  return (
    <section>
      <h2>Connect Google Analytics</h2>
      {authError && (
        <p className="form-error" role="alert">
          {authError}
        </p>
      )}
      {!connected ? (
        <button
          type="button"
          onClick={() => {
            window.location.href = `${apiBase}/api/auth/login`;
          }}
        >
          Connect GA4
        </button>
      ) : (
        <div className="stack">
          <div className="row">
            <span className="chip chip-ok">Connected</span>
            <button
              type="button"
              onClick={() => {
                window.location.href = `${apiBase}/api/auth/login`;
              }}
            >
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
          {propertyError && (
            <p className="form-error" role="alert">
              {propertyError}
            </p>
          )}
          <div className="stack">
            <label className="row">
              <input
                type="checkbox"
                checked={bqStreaming}
                onChange={(e) => setBqStreaming(e.target.checked)}
              />
              Enable streaming export (optional; may increase BigQuery cost)
            </label>
            <button
              type="button"
              onClick={handleLinkBigQuery}
              disabled={bqLinkLoading || !selectedPropertyId.trim()}
            >
              {bqLinkLoading
                ? "Linking BigQuery..."
                : "Link GA4 export to BigQuery"}
            </button>
            {bqLinkMessage && (
              <p className="form-success">{bqLinkMessage}</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
