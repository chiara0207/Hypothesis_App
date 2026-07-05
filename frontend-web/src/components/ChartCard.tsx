"use client";

import { useState } from "react";
import PlotlyChart, { type PlotlyFigure } from "@/components/PlotlyChart";
import { apiPost, ApiError } from "@/lib/api";

export type VizChart = {
  key: string;
  title: string;
  figure: PlotlyFigure;
  interpretation: string;
  handbook: { what?: string; how_to_read?: string; when_used?: string };
};

type ChatMessage = { role: "user" | "assistant"; content: string };

export default function ChartCard({
  chart,
  sessionId,
  testName,
  variablesUsed,
  pValue,
  alpha,
}: {
  chart: VizChart;
  sessionId: string;
  testName: string;
  variablesUsed: Record<string, string>;
  pValue: number | null | undefined;
  alpha: number;
}) {
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);

  async function ask() {
    const q = question.trim();
    if (!q || asking) return;
    const priorHistory = history;
    setHistory([...priorHistory, { role: "user", content: q }]);
    setQuestion("");
    setAsking(true);
    try {
      const res = await apiPost<{ answer: string }>("/visualization/ask", {
        session_id: sessionId,
        test_name: testName,
        variables_used: variablesUsed,
        chart_key: chart.key,
        question: q,
        history: priorHistory,
        p_value: pValue,
        alpha,
      });
      setHistory((h) => [...h, { role: "assistant", content: res.answer }]);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Something went wrong.";
      setHistory((h) => [...h, { role: "assistant", content: `⚠️ ${msg}` }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-bg-card p-4">
      <p className="mb-2 text-sm font-semibold text-text-primary">{chart.title}</p>
      <PlotlyChart figure={chart.figure} />
      {chart.interpretation && (
        <p className="mt-2 text-[0.85rem] text-text-secondary">{chart.interpretation}</p>
      )}

      {(chart.handbook.what || chart.handbook.how_to_read || chart.handbook.when_used) && (
        <details className="mt-3 border-t border-border pt-2.5">
          <summary className="cursor-pointer text-xs font-semibold text-text-muted">
            📖 Learn more about this chart type
          </summary>
          <div className="mt-2 space-y-1.5 text-[0.83rem] leading-relaxed text-text-secondary">
            {chart.handbook.what && (
              <p>
                <strong className="text-text-primary">What it is:</strong> {chart.handbook.what}
              </p>
            )}
            {chart.handbook.how_to_read && (
              <p>
                <strong className="text-text-primary">How to read it:</strong> {chart.handbook.how_to_read}
              </p>
            )}
            {chart.handbook.when_used && (
              <p>
                <strong className="text-text-primary">When it&apos;s used:</strong> {chart.handbook.when_used}
              </p>
            )}
          </div>
        </details>
      )}

      <details className="mt-3 border-t border-border pt-2.5">
        <summary className="cursor-pointer text-xs font-semibold text-text-muted">
          💬 Ask about this chart
        </summary>
        <div className="mt-2.5 space-y-2">
          {history.map((m, i) => (
            <div
              key={i}
              className={`rounded-md px-3 py-2 text-[0.83rem] ${
                m.role === "user" ? "bg-bg-card-alt text-text-primary" : "bg-bg-app text-text-secondary"
              }`}
            >
              {m.content}
            </div>
          ))}
          {asking && <p className="text-xs text-text-muted">Thinking…</p>}
          <div className="flex gap-2">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              placeholder="e.g. Why is the Treatment box higher than Control?"
              className="flex-1 rounded-md border border-border-strong bg-bg-app px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
            <button
              onClick={ask}
              disabled={asking || !question.trim()}
              className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
            >
              Ask
            </button>
          </div>
        </div>
      </details>
    </div>
  );
}
