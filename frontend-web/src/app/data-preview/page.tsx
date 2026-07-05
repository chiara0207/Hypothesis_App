"use client";

import { useAppStore } from "@/lib/store";

export default function DataPreviewPage() {
  const { csvSessionId, csvFilename, csvRows, csvColumns, csvDtypes, csvPreview } = useAppStore();

  return (
    <div>
      <h2 className="mb-4 text-2xl font-semibold text-text-primary">Dataset preview</h2>

      {!csvSessionId ? (
        <div className="rounded-lg border border-accent-soft bg-accent-soft px-4 py-3 text-sm text-accent-hover">
          Upload a CSV or XLSX file in the sidebar to see a preview here.
        </div>
      ) : (
        <>
          <p className="mb-4 text-sm text-text-secondary">
            <span className="font-semibold text-text-primary">{csvFilename}</span> · {csvRows} rows ·{" "}
            {csvColumns.length} columns
          </p>

          <p className="mb-2 text-sm font-semibold text-text-primary">Preview</p>
          <div className="mb-6 overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-bg-card-alt text-text-secondary">
                <tr>
                  {csvColumns.map((col) => (
                    <th key={col} className="px-3 py-2 font-semibold whitespace-nowrap">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {csvPreview.map((row, i) => (
                  <tr key={i} className="border-t border-border">
                    {csvColumns.map((col) => (
                      <td key={col} className="px-3 py-2 whitespace-nowrap text-text-secondary">
                        {row[col]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mb-2 text-sm font-semibold text-text-primary">Column types</p>
          <div className="overflow-hidden rounded-xl border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-bg-card-alt text-text-secondary">
                <tr>
                  <th className="px-3 py-2 font-semibold">Column</th>
                  <th className="px-3 py-2 font-semibold">Type</th>
                </tr>
              </thead>
              <tbody>
                {csvColumns.map((col) => (
                  <tr key={col} className="border-t border-border">
                    <td className="px-3 py-2 text-text-primary">{col}</td>
                    <td className="px-3 py-2 text-text-secondary">{csvDtypes[col]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
