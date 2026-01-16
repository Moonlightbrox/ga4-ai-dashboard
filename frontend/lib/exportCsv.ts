export function exportToCSV(
  data: Array<Record<string, unknown>> | undefined | null,
  filename: string
): void {
  if (!data || data.length === 0) {
    return;
  }

  const headers = Object.keys(data[0] ?? {});
  if (headers.length === 0) {
    return;
  }

  const escapeValue = (value: unknown) => {
    const stringValue = value == null ? "" : String(value);
    const needsQuotes = /[",\n\r]/.test(stringValue);
    const escaped = stringValue.replace(/"/g, '""');
    return needsQuotes ? `"${escaped}"` : escaped;
  };

  const lines = [
    headers.join(","),
    ...data.map((row) =>
      headers.map((header) => escapeValue(row[header])).join(",")
    ),
  ];

  const csvContent = `\uFEFF${lines.join("\r\n")}`;
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
