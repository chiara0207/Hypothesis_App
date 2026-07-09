"use client";

import { useEffect, useState } from "react";
import { apiPost, ApiError } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { StatTestResult } from "@/lib/types";
import ChartCard, { type VizChart } from "@/components/ChartCard";

export default function StatisticalAnalysisPage() {
  const { csvSessionId, csvFilename, csvRows, csvColumns, lastStatsResult, setLastStatsResult, statsHistory, addStatsHistory, clearStatsHistory } =
    useAppStore();

  const [alpha, setAlpha] = useState(0.05);
  const [question, setQuestion] = useState("");
  const [examples, setExamples] = useState<string[] | null>(null);
  const [examplesLoading, setExamplesLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [charts, setCharts] = useState<VizChart[] | null>(null);
  const [chartsLoading, setChartsLoading] = useState(false);

  // examples is only ever rendered when csvSessionId is set (see JSX below),
  // so there's no need to reset it back to null when the session clears.
  useEffect(() => {
    if (!csvSessionId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExamplesLoading(true);
    apiPost<{ questions: string[] }>("/stats/examples", { session_id: csvSessionId, n: 6 })
      .then((res) => setExamples(res.questions))
      .catch(() => setExamples([]))
      .finally(() => setExamplesLoading(false));
  }, [csvSessionId]);

  // charts are only ever rendered inside ResultView's success branch, which
  // never runs for "unsupported"/error results, so stale charts left in
  // state from a prior run are simply never displayed.
  useEffect(() => {
    if (!csvSessionId || !lastStatsResult || lastStatsResult.test_name === "unsupported" || lastStatsResult.error) {
      return;
    }
    // React's documented fetch-in-effect pattern (flip a loading flag, then fetch);
    // no data-fetching library is in scope for this migration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setChartsLoading(true);
    apiPost<{ charts: VizChart[] }>("/visualization/suite", {
      session_id: csvSessionId,
      test_name: lastStatsResult.test_name,
      variables_used: lastStatsResult.variables_used,
      p_value: lastStatsResult.p_value,
      alpha: lastStatsResult.alpha,
    })
      .then((res) => setCharts(res.charts))
      .catch(() => setCharts([]))
      .finally(() => setChartsLoading(false));
  }, [lastStatsResult, csvSessionId]);

  async function runAnalysis() {
    if (!csvSessionId || !question.trim()) return;
    setRunning(true);
    setRunError("");
    try {
      const result = await apiPost<StatTestResult>("/stats/analyze", {
        session_id: csvSessionId,
        question,
      });
      setLastStatsResult(result);
      if (result.test_name !== "unsupported" && !result.error) {
        addStatsHistory({ question, result, sessionId: csvSessionId });
      }
    } catch (e) {
      setRunError(e instanceof ApiError ? e.message : "Analysis failed.");
    } finally {
      setRunning(false);
    }
  }

  function exportHistoryCsv() {
    const headers = [
      "Question",
      "Test",
      "Variables",
      "p-value",
      "Test Statistic",
      "Alpha",
      "Significant",
      "Detailed Statistics",
      "Assumption Checks",
      "Interpretation",
      "Plain Explanation",
      "Rationale",
    ];
    const rows = statsHistory.map((h) => [
      h.question,
      h.result.test_display_name,
      Object.entries(h.result.variables_used)
        .map(([role, col]) => `${role}=${col}`)
        .join("; "),
      h.result.p_value ?? "",
      h.result.statistic ?? "",
      h.result.alpha,
      h.result.significant ?? "",
      Object.keys(h.result.additional_stats ?? {}).length > 0 ? JSON.stringify(h.result.additional_stats) : "",
      h.result.assumption_checks.length > 0
        ? h.result.assumption_checks.map((c) => `${c.name}: ${c.passed ? "passed" : "failed"} (${c.detail})`).join("; ")
        : "",
      h.result.interpretation,
      h.result.plain_explanation,
      h.result.rationale,
    ]);
    const csv = [headers, ...rows]
      .map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "analysis_results.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="mb-6 rounded-2xl border border-border-strong bg-gradient-to-br from-[#1a2340] to-[#24305a] p-5">
        <h3 className="mb-1 text-xl font-semibold text-white">Statistical Analysis</h3>
        <p className="text-sm text-white/85">
          Ask a question in plain language — the AI selects the test, runs it, and explains the results.
        </p>
        {csvSessionId && (
          <span className="mt-3 inline-block rounded-full border border-white/20 bg-white/10 px-3.5 py-1.5 text-sm text-[#dbe2f5]">
            📊 {csvFilename} · {csvRows.toLocaleString()} rows · {csvColumns.length} columns
          </span>
        )}
      </div>

      {!csvSessionId ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-bg-card px-6 py-10 text-center">
          <h4 className="mb-2 text-lg font-semibold text-text-primary">No dataset loaded</h4>
          <p className="text-sm text-text-secondary">
            Upload a CSV or XLSX file in the sidebar to run hypothesis tests.
          </p>
        </div>
      ) : (
        <>
          <div className="mb-6 rounded-xl border border-border bg-bg-card p-5">
            {examplesLoading && (
              <p className="mb-4 text-xs font-bold tracking-wider text-text-muted uppercase">
                Generating example questions for your dataset…
              </p>
            )}
            {!examplesLoading && examples && examples.length > 0 && (
              <details className="mb-4">
                <summary className="cursor-pointer text-xs font-bold tracking-wider text-text-muted uppercase">
                  Suggested questions
                </summary>
                <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {examples.map((ex, i) => (
                    <button
                      key={i}
                      onClick={() => setQuestion(ex)}
                      className="rounded-lg border border-border-strong px-3.5 py-2 text-left text-sm text-text-primary hover:bg-bg-card-alt"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </details>
            )}

            <p className="mb-1.5 text-xs font-bold tracking-wider text-text-muted uppercase">Your analysis</p>
            <p className="mb-3 text-sm text-text-secondary">
              Describe what you want to test — comparisons, correlations, regression, or associations. Use
              exact column names when possible.
            </p>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. Does smoking predict disease?"
              rows={3}
              className="mb-3 w-full resize-y rounded-lg border border-border-strong bg-bg-app px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
            <div className="flex items-end gap-3">
              <div>
                <label className="mb-1 block text-xs text-text-secondary">Significance level (α)</label>
                <select
                  value={alpha}
                  onChange={(e) => setAlpha(Number(e.target.value))}
                  className="rounded-lg border border-border-strong bg-bg-app px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                >
                  {[0.05, 0.01, 0.1].map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={runAnalysis}
                disabled={running || !question.trim()}
                className="rounded-lg bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
              >
                {running ? "Selecting test · Running analysis…" : "Run Analysis"}
              </button>
            </div>
          </div>

          {runError && (
            <div className="mb-5 rounded-lg border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger-text">
              {runError}
            </div>
          )}

          {lastStatsResult && (
            <ResultView result={lastStatsResult} charts={charts} chartsLoading={chartsLoading} csvSessionId={csvSessionId} />
          )}

          {statsHistory.length > 0 && (
            <div className="mt-8">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-xs font-bold tracking-wider text-text-muted uppercase">Session history</p>
                <div className="flex gap-2">
                  <button
                    onClick={exportHistoryCsv}
                    className="rounded-md border border-border-strong px-3 py-1.5 text-xs text-text-primary hover:bg-bg-card-alt"
                  >
                    Export CSV
                  </button>
                  <button
                    onClick={clearStatsHistory}
                    className="rounded-md border border-border-strong px-3 py-1.5 text-xs text-text-primary hover:bg-bg-card-alt"
                  >
                    Clear history
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                {[...statsHistory].reverse().slice(0, 5).map((h, i) => (
                  <details key={i} className="rounded-lg border border-border bg-bg-card px-4 py-2.5">
                    <summary className="cursor-pointer text-sm text-text-primary">
                      {h.result.test_display_name} · p ={" "}
                      {h.result.p_value != null ? h.result.p_value.toFixed(4) : "N/A"}
                    </summary>
                    <div className="mt-2 border-t border-border pt-2 text-sm text-text-secondary">
                      <p className="mb-1">
                        <strong className="text-text-primary">Question:</strong> {h.question}
                      </p>
                      <p>{h.result.plain_explanation}</p>
                    </div>
                  </details>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ResultView({
  result,
  charts,
  chartsLoading,
  csvSessionId,
}: {
  result: StatTestResult;
  charts: VizChart[] | null;
  chartsLoading: boolean;
  csvSessionId: string;
}) {
  if (result.test_name === "unsupported") {
    return (
      <div className="rounded-lg border border-warning-border bg-warning-bg px-4 py-3 text-sm text-warning-text">
        <strong>Not supported</strong>
        <p className="mt-1">{result.plain_explanation || result.error}</p>
      </div>
    );
  }
  if (result.error) {
    return (
      <div className="rounded-lg border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger-text">
        <strong>Analysis could not be completed</strong>
        <p className="mt-1">{result.error}</p>
      </div>
    );
  }

  const kpis: [string, string][] = [
    ["p-value", result.p_value != null ? result.p_value.toFixed(4) : "—"],
    ["Test statistic", result.statistic != null ? result.statistic.toFixed(4) : "—"],
    ["α (alpha)", String(result.alpha)],
  ];
  const add = result.additional_stats ?? {};
  if ("n" in add) kpis.push(["Sample size (n)", String(add.n)]);
  if ("r_squared" in add) kpis.push(["R²", String(add.r_squared)]);
  if ("pseudo_r_squared" in add) kpis.push(["Pseudo R²", String(add.pseudo_r_squared)]);

  return (
    <div className="rounded-2xl border border-border bg-bg-card p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <span className="rounded-lg bg-accent px-3.5 py-1.5 text-sm font-semibold text-white">
          {result.test_display_name}
        </span>
        {result.significant === true && (
          <span className="rounded-full border border-success-border bg-success-bg px-3 py-1 text-xs font-bold text-success-text">
            Statistically significant
          </span>
        )}
        {result.significant === false && (
          <span className="rounded-full border border-danger-border bg-danger-bg px-3 py-1 text-xs font-bold text-danger-text">
            Not significant
          </span>
        )}
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:grid-cols-6">
        {kpis.slice(0, 6).map(([label, value]) => (
          <div key={label} className="rounded-lg border border-border border-l-4 border-l-accent bg-bg-card-alt px-3 py-2.5">
            <p className="text-[0.68rem] font-semibold tracking-wide text-text-secondary uppercase">{label}</p>
            <p className="text-lg font-bold text-text-primary">{value}</p>
          </div>
        ))}
      </div>

      {chartsLoading && <p className="mb-4 text-sm text-text-muted">Loading visualizations…</p>}
      {charts && charts.length > 0 && (
        <div className="mb-5">
          <p className="mb-2.5 text-xs font-bold tracking-wider text-text-muted uppercase">Visualizations</p>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {charts.map((c) => (
              <ChartCard
                key={c.key}
                chart={c}
                sessionId={csvSessionId}
                testName={result.test_name}
                variablesUsed={result.variables_used}
                pValue={result.p_value}
                alpha={result.alpha}
              />
            ))}
          </div>
        </div>
      )}

      {result.rationale && (
        <div className="mb-4 rounded-lg border border-border border-l-4 border-l-accent bg-bg-card-alt px-4 py-3 text-sm text-text-secondary">
          <strong className="text-text-primary">Why this test?</strong> {result.rationale}
        </div>
      )}

      {Object.keys(result.variables_used).length > 0 && (
        <div className="mb-4">
          <p className="mb-2 text-xs font-bold tracking-wider text-text-muted uppercase">Variables</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(result.variables_used).map(([role, col]) => (
              <span key={role} className="rounded-md border border-border-strong bg-bg-card-alt px-2.5 py-1 text-sm text-text-primary">
                <span className="mr-1.5 text-xs font-semibold text-text-muted uppercase">{role}</span>
                {col}
              </span>
            ))}
          </div>
        </div>
      )}

      {Object.keys(add).length > 0 && (
        <div className="mb-4">
          <AdditionalStatsPanel stats={add} />
        </div>
      )}

      {result.assumption_checks.length > 0 && (
        <details className="mb-4 rounded-lg border border-border bg-bg-card-alt px-4 py-3">
          <summary className="cursor-pointer text-sm font-semibold text-text-primary">Assumption checks</summary>
          <div className="mt-2.5 space-y-2">
            {result.assumption_checks.map((c, i) => (
              <div
                key={i}
                className={`rounded-lg border px-3.5 py-2.5 text-sm ${
                  c.passed ? "border-success-border bg-success-bg text-[#a9e8cd]" : "border-warning-border bg-warning-bg text-[#f3d78c]"
                }`}
              >
                <strong className="text-text-primary">{c.passed ? "✓" : "!"} {c.name}</strong>
                <p>{c.detail}</p>
              </div>
            ))}
          </div>
        </details>
      )}

      <p className="mb-2 text-xs font-bold tracking-wider text-text-muted uppercase">Interpretation</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-bg-card-alt p-3.5">
          <p className="mb-1.5 text-xs font-semibold text-text-muted">Technical</p>
          <p className="text-sm text-text-secondary">{result.interpretation}</p>
        </div>
        <div className="rounded-lg border border-border bg-bg-card-alt p-3.5">
          <p className="mb-1.5 text-xs font-semibold text-text-muted">Plain language</p>
          <p className="text-sm text-text-secondary">{result.plain_explanation}</p>
        </div>
      </div>
    </div>
  );
}

const NESTED_KEYS: Record<string, string> = {
  contingency_table: "Contingency table",
  group_stats: "Group statistics",
  coefficients: "Coefficients",
};

function AdditionalStatsPanel({ stats }: { stats: Record<string, unknown> }) {
  const nested = Object.keys(NESTED_KEYS).filter((k) => stats[k] && typeof stats[k] === "object");
  const scalarEntries = Object.entries(stats).filter(([k, v]) => !(k in NESTED_KEYS) && typeof v !== "object");

  return (
    <details className="rounded-lg border border-border bg-bg-card-alt px-4 py-3">
      <summary className="cursor-pointer text-sm font-semibold text-text-primary">Detailed statistics</summary>
      <div className="mt-3 space-y-4">
        {nested.map((k) => (
          <div key={k}>
            <p className="mb-1.5 text-xs font-semibold text-text-secondary">{NESTED_KEYS[k]}</p>
            <NestedTable data={stats[k] as Record<string, Record<string, unknown>>} />
          </div>
        ))}
        {scalarEntries.length > 0 && (
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            {scalarEntries.map(([k, v]) => (
              <div key={k} className="rounded-lg border border-border bg-bg-card px-3 py-2">
                <p className="text-[0.66rem] font-semibold tracking-wide text-text-muted uppercase">
                  {k.replace(/_/g, " ")}
                </p>
                <p className="text-sm font-semibold text-text-primary">{String(v)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

function NestedTable({ data }: { data: Record<string, Record<string, unknown>> }) {
  const outerKeys = Object.keys(data);
  const innerKeys = Array.from(new Set(outerKeys.flatMap((k) => Object.keys(data[k] ?? {}))));
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-xs">
        <thead className="bg-bg-card text-text-secondary">
          <tr>
            <th className="px-2.5 py-1.5"></th>
            {outerKeys.map((k) => (
              <th key={k} className="px-2.5 py-1.5 font-semibold whitespace-nowrap">
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {innerKeys.map((ik) => (
            <tr key={ik} className="border-t border-border">
              <td className="px-2.5 py-1.5 font-semibold whitespace-nowrap text-text-primary">{ik}</td>
              {outerKeys.map((ok) => (
                <td key={ok} className="px-2.5 py-1.5 whitespace-nowrap text-text-secondary">
                  {String(data[ok]?.[ik] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
