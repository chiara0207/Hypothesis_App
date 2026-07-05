"use client";

import { useState } from "react";
import { apiPost, ApiError } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type Source = { id: string; text: string; score: number };
type ChatMessage = { role: "user" | "assistant"; content: string; sources?: Source[] };

const STARTER_PROMPTS = [
  "What is the main research question or objective?",
  "What methodology or study design was used?",
  "Summarize the key findings in a few sentences.",
  "What limitations does the author discuss?",
];

export default function AskQuestionsPage() {
  const { pdfUploaded, pdfFilename } = useAppStore();
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function ask(question: string) {
    if (!question.trim() || sending || !pdfUploaded) return;
    setHistory((h) => [...h, { role: "user", content: question }]);
    setInput("");
    setSending(true);
    try {
      const res = await apiPost<{ answer: string; sources: Source[] }>("/qa/ask", {
        question,
        top_k: 5,
      });
      setHistory((h) => [...h, { role: "assistant", content: res.answer, sources: res.sources }]);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Something went wrong.";
      setHistory((h) => [...h, { role: "assistant", content: `⚠️ ${msg}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div>
      <div className="mb-6 rounded-2xl border border-border-strong bg-gradient-to-br from-[#1a2340] to-[#24305a] p-5">
        <h3 className="mb-1 text-xl font-semibold text-white">Document Q&amp;A</h3>
        <p className="text-sm text-white/85">
          Ask natural-language questions about your research PDF. Answers are grounded in retrieved
          passages from the indexed document.
        </p>
        {pdfUploaded && (
          <span className="mt-3 inline-block rounded-full border border-white/20 bg-white/10 px-3.5 py-1.5 text-sm text-[#dbe2f5]">
            📄 {pdfFilename}
          </span>
        )}
      </div>

      {!pdfUploaded ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-bg-card px-6 py-10 text-center">
          <h4 className="mb-2 text-lg font-semibold text-text-primary">No document loaded yet</h4>
          <p className="text-sm text-text-secondary">
            Upload a research PDF in the sidebar to index it for semantic search and chat.
          </p>
        </div>
      ) : (
        <>
          {history.length === 0 && (
            <div className="mb-5 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {STARTER_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => ask(p)}
                  className="rounded-lg border border-border-strong px-4 py-3 text-left text-sm text-text-primary transition-colors hover:bg-bg-card-alt"
                >
                  {p}
                </button>
              ))}
            </div>
          )}

          <div className="space-y-3">
            {history.map((m, i) => (
              <div
                key={i}
                className={`rounded-xl border border-border px-4 py-3 text-sm leading-relaxed ${
                  m.role === "user" ? "bg-bg-card-alt text-text-primary" : "bg-bg-card text-text-secondary"
                }`}
              >
                <p>{m.content}</p>
                {m.sources && m.sources.length > 0 && (
                  <details className="mt-3 border-t border-border pt-2.5">
                    <summary className="cursor-pointer text-xs font-semibold text-text-muted">
                      📎 {m.sources.length} document citation{m.sources.length !== 1 ? "s" : ""}
                    </summary>
                    <div className="mt-2.5 space-y-2">
                      {m.sources.map((s, si) => (
                        <div
                          key={si}
                          className="rounded-lg border border-border border-l-4 border-l-accent bg-bg-card-alt px-3.5 py-3"
                        >
                          <div className="mb-1.5 flex items-center gap-2">
                            <span className="flex h-5 min-w-5 items-center justify-center rounded-md bg-accent px-1 text-[0.72rem] font-bold text-white">
                              {si + 1}
                            </span>
                            <div className="h-1.5 max-w-[140px] flex-1 overflow-hidden rounded-full bg-border">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-accent to-accent-hover"
                                style={{ width: `${Math.round(s.score * 100)}%` }}
                              />
                            </div>
                            <span className="text-xs font-semibold text-accent-hover">
                              {Math.round(s.score * 100)}%
                            </span>
                          </div>
                          <p className="text-[0.85rem] text-text-secondary">{s.text.slice(0, 320)}</p>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            ))}
            {sending && <div className="text-sm text-text-muted">Searching document and generating answer…</div>}
          </div>

          <div className="mt-6 flex gap-2.5">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask(input)}
              placeholder="Ask about methodology, findings, limitations…"
              className="flex-1 rounded-full border border-border-strong bg-bg-card px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
            <button
              onClick={() => ask(input)}
              disabled={sending || !input.trim()}
              className="rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
            >
              ↑
            </button>
          </div>
        </>
      )}
    </div>
  );
}
