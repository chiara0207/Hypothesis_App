"use client";

import { useEffect, useState } from "react";
import { ChevronRight, Send } from "lucide-react";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type Concept = {
  key: string;
  title: string;
  category: "concept" | "test";
  what: string;
  why_it_matters: string;
  example: string;
};

type ChatMessage = { role: "user" | "assistant"; content: string };

const STARTER_QUESTIONS = [
  "What is a p-value?",
  "What's the difference between a t-test and ANOVA?",
  "What does 'statistically significant' actually mean?",
];

export default function HandbookPage() {
  const lastStatsResult = useAppStore((s) => s.lastStatsResult);
  const groundable = Boolean(
    lastStatsResult && lastStatsResult.test_name !== "unsupported" && !lastStatsResult.error,
  );

  const [concepts, setConcepts] = useState<Concept[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [asking, setAsking] = useState(false);
  const [groundInResult, setGroundInResult] = useState(true);

  useEffect(() => {
    apiGet<{ concepts: Concept[] }>("/handbook/concepts")
      .then((res) => setConcepts(res.concepts))
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Failed to load handbook."));
  }, []);

  async function ask(q: string) {
    if (!q.trim() || asking) return;
    const priorHistory = history;
    setHistory([...priorHistory, { role: "user", content: q }]);
    setQuestion("");
    setAsking(true);
    try {
      const payload: Record<string, unknown> = { question: q, history: priorHistory };
      if (groundable && groundInResult && lastStatsResult) {
        payload.test_name = lastStatsResult.test_name;
        payload.variables_used = lastStatsResult.variables_used;
        payload.rationale = lastStatsResult.rationale;
        payload.statistic = lastStatsResult.statistic;
        payload.p_value = lastStatsResult.p_value;
        payload.alpha = lastStatsResult.alpha;
        payload.significant = lastStatsResult.significant;
        payload.assumption_checks = lastStatsResult.assumption_checks;
      }
      const res = await apiPost<{ answer: string }>("/handbook/ask", payload);
      setHistory((h) => [...h, { role: "assistant", content: res.answer }]);
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Something went wrong.";
      setHistory((h) => [...h, { role: "assistant", content: `⚠️ ${message}` }]);
    } finally {
      setAsking(false);
    }
  }

  const lastAnswer = [...history].reverse().find((m) => m.role === "assistant")?.content;
  const coreConcepts = concepts?.filter((c) => c.category === "concept") ?? [];
  const testConcepts = concepts?.filter((c) => c.category === "test") ?? [];

  return (
    <div>
      <h2 className="mb-1 text-2xl font-semibold text-text-primary">Stats handbook</h2>
      <p className="mb-5 text-sm text-text-secondary">
        Look up core concepts in plain language, or ask about a specific term.
      </p>

      <div className="mb-6 rounded-2xl border border-border bg-bg-card p-5">
        <div className="mb-0.5 flex items-center gap-2 font-bold text-text-primary">
          <span className="text-red-500">❓</span> Ask about a concept
        </div>
        <p className="mb-3.5 text-sm text-text-secondary">
          e.g. &quot;What&apos;s the difference between a t-test and ANOVA?&quot;
        </p>

        <div className="flex gap-2.5">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask(question)}
            placeholder="What is a p-value?"
            className="flex-1 rounded-lg border border-border-strong bg-bg-app px-3.5 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
          />
          <button
            onClick={() => ask(question)}
            disabled={asking || !question.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send size={14} /> Ask
          </button>
        </div>

        {groundable && (
          <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-text-secondary">
            <input
              type="checkbox"
              checked={groundInResult}
              onChange={(e) => setGroundInResult(e.target.checked)}
              className="accent-accent"
            />
            Ground answers in my last result ({lastStatsResult?.test_display_name})
          </label>
        )}

        {history.length === 0 ? (
          <div className="mt-3.5 flex flex-wrap gap-2.5">
            {STARTER_QUESTIONS.map((sq) => (
              <button
                key={sq}
                onClick={() => ask(sq)}
                disabled={asking}
                className="rounded-lg border border-border-strong px-3.5 py-2 text-sm text-text-primary transition-colors hover:bg-bg-card-alt disabled:opacity-50"
              >
                {sq}
              </button>
            ))}
          </div>
        ) : (
          <>
            <div className="mt-3.5 rounded-lg border border-border bg-bg-card-alt px-4 py-4 text-sm leading-relaxed text-text-secondary">
              {asking ? "Thinking…" : lastAnswer}
            </div>
            <button
              onClick={() => setHistory([])}
              className="mt-3 rounded-lg border border-border-strong px-3.5 py-1.5 text-sm text-text-secondary hover:bg-bg-card-alt"
            >
              Clear chat
            </button>
          </>
        )}
      </div>

      {loadError && (
        <div className="mb-5 rounded-lg border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger-text">
          {loadError}
        </div>
      )}

      <SectionLabel>Core concepts</SectionLabel>
      <ConceptGrid items={coreConcepts} icon="📘" />

      <SectionLabel>Hypothesis tests</SectionLabel>
      <ConceptGrid items={testConcepts} icon="🧪" moreLabel="When to use it" />
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-6 mb-2.5 text-xs font-bold tracking-wider text-text-muted uppercase">
      {children}
    </p>
  );
}

function ConceptGrid({
  items,
  icon,
  moreLabel = "Why it matters",
}: {
  items: Concept[];
  icon: string;
  moreLabel?: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-text-muted">Loading…</p>;
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {items.map((c) => (
        <div key={c.key} className="rounded-xl border border-border bg-bg-card p-4">
          <div className="mb-1.5 flex items-center gap-2 text-sm font-bold text-text-primary">
            <span className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[7px] bg-accent-soft text-sm">
              {icon}
            </span>
            {c.title}
          </div>
          <p className="text-[0.86rem] leading-relaxed text-text-secondary">{c.what}</p>
          <details className="group mt-2.5">
            <summary className="flex cursor-pointer list-none items-center gap-1 text-sm text-text-secondary hover:text-text-primary">
              <ChevronRight size={14} className="transition-transform group-open:rotate-90" />
              More
            </summary>
            <div className="mt-2.5 space-y-1.5 border-t border-border pt-2.5 text-[0.86rem] leading-relaxed text-text-secondary">
              <p>
                <strong className="text-text-primary">{moreLabel}:</strong> {c.why_it_matters}
              </p>
              <p>
                <strong className="text-text-primary">Example:</strong> {c.example}
              </p>
            </div>
          </details>
        </div>
      ))}
    </div>
  );
}
