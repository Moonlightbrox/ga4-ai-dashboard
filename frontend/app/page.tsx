"use client";

/**
 * BigQuery analyst dashboard -- composition only.
 *
 * Owns just enough state to know when the user has authenticated to
 * Google and selected a GA4 property, then mounts the analyst surface
 * (two Deep Scan buttons + the unified chat + the read-only prompt
 * viewer). Everything heavier lives in dedicated components so this
 * file stays a pure layout shell.
 */

import { useCallback, useState } from "react";

import { AgentChat } from "../components/AgentChat";
import { AiPromptViewer } from "../components/AiPromptViewer";
import {
  DeepScan,
  GAME_DEEP_SCAN_CONFIG,
  SITE_DEEP_SCAN_CONFIG,
} from "../components/DeepScan";
import { PropertyPicker } from "../components/PropertyPicker";


export default function HomePage() {
  const [ready, setReady] = useState(false);

  const handleReadyChange = useCallback((isReady: boolean) => {
    setReady(isReady);
  }, []);

  return (
    <main>
      <h1>BigQuery Analyst</h1>
      <p>
        Connect Google Analytics, point us at the GA4 property whose BigQuery
        export you want analyzed, then run a Deep Scan or just ask a
        question. Two specialized agents live here: a Web Analyst for site
        behaviour and a Game Analyst for retention and gameplay.
      </p>

      <PropertyPicker onReadyChange={handleReadyChange} />

      {ready ? (
        <>
          <DeepScan config={SITE_DEEP_SCAN_CONFIG} />
          <DeepScan config={GAME_DEEP_SCAN_CONFIG} />
          <AgentChat />
          <AiPromptViewer />
        </>
      ) : (
        <section>
          <p>
            Pick a GA4 property above to unlock Deep Scans and chat. Both
            analysts read from your project&apos;s BigQuery dataset, so you
            also need the GA4 -&gt; BigQuery export linked at least once
            before running.
          </p>
        </section>
      )}
    </main>
  );
}
