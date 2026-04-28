"use client";

/**
 * AnswerRenderer -- the single answer formatter used by both the
 * Deep Scan buttons and the agent chat. Extracted from the original
 * DeepScan.tsx parser so the same look-and-feel applies regardless of
 * how the answer was triggered.
 *
 * Supports a deliberately small subset of markdown:
 *   - ATX-style headings (#..######) collapse to <h3>/<h4>.
 *   - Bullet lists (- or *) -> <ul>.
 *   - GitHub-style pipe tables with a separator row -> <table>.
 *   - Italic-only line ("*Window: ...*") -> emphasized meta paragraph.
 *   - Blank-line-separated paragraphs.
 *
 * Intentionally does NOT support inline bold/italic spans, nested lists,
 * code blocks, or links. The orchestrator prompts produce plain narrative;
 * anything richer is a prompt-side concern, not a renderer bug.
 */

import { useMemo } from "react";


type ReportBlock =
  | { kind: "heading"; level: 2 | 3; text: string }
  | { kind: "paragraph"; text: string; emphasis?: boolean }
  | { kind: "list"; items: string[] }
  | { kind: "table"; headers: string[]; rows: string[][] };

function parseTableRow(line: string): string[] {
  const stripped = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return stripped.split("|").map((c) => c.trim());
}

function isTableSeparator(line: string): boolean {
  return /^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/.test(line);
}

function isBullet(line: string): boolean {
  return /^\s*[-*]\s+/.test(line);
}

function stripInlineMarkdown(value: string): string {
  return value
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

export function parseAnswer(markdown: string): ReportBlock[] {
  const lines = String(markdown ?? "").split(/\r?\n/);
  const blocks: ReportBlock[] = [];
  let i = 0;
  while (i < lines.length) {
    const raw = lines[i];
    const line = raw.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      i += 1;
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (headingMatch) {
      const level = headingMatch[1].length <= 2 ? 2 : 3;
      blocks.push({
        kind: "heading",
        level,
        text: stripInlineMarkdown(headingMatch[2]),
      });
      i += 1;
      continue;
    }

    const next = lines[i + 1]?.trim() ?? "";
    if (trimmed.includes("|") && isTableSeparator(next)) {
      const headers = parseTableRow(trimmed).map(stripInlineMarkdown);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
        rows.push(parseTableRow(lines[i]).map(stripInlineMarkdown));
        i += 1;
      }
      blocks.push({ kind: "table", headers, rows });
      continue;
    }

    if (isBullet(trimmed)) {
      const items: string[] = [];
      while (i < lines.length) {
        const curr = lines[i].trim();
        if (!isBullet(curr)) break;
        items.push(stripInlineMarkdown(curr.replace(/^\s*[-*]\s+/, "")));
        i += 1;
      }
      blocks.push({ kind: "list", items });
      continue;
    }

    const italicsOnly = trimmed.match(/^\*([^*]+)\*$/);
    if (italicsOnly) {
      blocks.push({
        kind: "paragraph",
        text: stripInlineMarkdown(italicsOnly[1]),
        emphasis: true,
      });
      i += 1;
      continue;
    }

    const paragraphLines: string[] = [];
    while (i < lines.length) {
      const p = lines[i].trim();
      if (!p) break;
      if (paragraphLines.length > 0) {
        if (p.match(/^(#{1,6})\s+/)) break;
        if (isBullet(p)) break;
        const lookahead = lines[i + 1]?.trim() ?? "";
        if (p.includes("|") && isTableSeparator(lookahead)) break;
      }
      paragraphLines.push(stripInlineMarkdown(p));
      i += 1;
    }
    if (paragraphLines.length > 0) {
      blocks.push({ kind: "paragraph", text: paragraphLines.join(" ") });
    } else {
      i += 1;
    }
  }
  return blocks;
}


export function AnswerRenderer({
  markdown,
}: {
  markdown: string | null | undefined;
}) {
  const raw = String(markdown ?? "");
  const blocks = useMemo(() => parseAnswer(raw), [raw]);
  if (!raw.trim()) {
    return (
      <p className="deep-scan-paragraph form-error" role="status">
        The run completed but there is no report text in the response. This
        usually means the model stopped without writing the narrative (check
        agent trace or backend logs). It is not a display bug: the answer
        field was empty.
      </p>
    );
  }
  if (blocks.length === 0) {
    return (
      <div className="deep-scan-report">
        <p className="deep-scan-paragraph" role="status">
          The report body could not be parsed into the normal headings /
          tables view (unusual format). Raw text is shown below.
        </p>
        <pre className="deep-scan-raw-fallback">{raw}</pre>
      </div>
    );
  }
  return (
    <article className="deep-scan-report">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return block.level === 2 ? (
            <h3 key={index} className="deep-scan-heading-2">
              {block.text}
            </h3>
          ) : (
            <h4 key={index} className="deep-scan-heading-3">
              {block.text}
            </h4>
          );
        }
        if (block.kind === "paragraph") {
          return (
            <p
              key={index}
              className={
                block.emphasis
                  ? "deep-scan-paragraph deep-scan-meta-line"
                  : "deep-scan-paragraph"
              }
            >
              {block.text}
            </p>
          );
        }
        if (block.kind === "list") {
          return (
            <ul key={index} className="deep-scan-list">
              {block.items.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          );
        }
        return (
          <div key={index} className="deep-scan-table-wrap">
            <table className="deep-scan-table">
              <thead>
                <tr>
                  {block.headers.map((h, idx) => (
                    <th key={idx}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIdx) => (
                  <tr key={rowIdx}>
                    {row.map((cell, cellIdx) => (
                      <td key={cellIdx}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </article>
  );
}
