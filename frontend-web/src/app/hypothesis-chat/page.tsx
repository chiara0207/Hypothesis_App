"use client";

import { useState } from "react";
import { apiPost, ApiError } from "@/lib/api";

type ChatMessage = { role: "user" | "assistant"; content: string };

const STARTER_HYPOTHESES = [
  "Will there be unicorns one day?",
  "Could humans ever photosynthesize like plants?",
  "Is consciousness just an illusion?",
  "Will AI become smarter than all humans combined?",
];

export default function HypothesisChatPage() {
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function send(message: string) {
    if (!message.trim() || sending) return;
    const priorHistory = history;
    setHistory([...priorHistory, { role: "user", content: message }]);
    setInput("");
    setSending(true);
    try {
      const res = await apiPost<{ reply: string }>("/chat/message", {
        message,
        history: priorHistory,
      });
      setHistory((h) => [...h, { role: "assistant", content: res.reply }]);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Something went wrong.";
      setHistory((h) => [...h, { role: "assistant", content: `⚠️ ${msg}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-6 rounded-2xl border border-border-strong bg-gradient-to-br from-[#1a2340] to-[#24305a] p-5">
        <h3 className="mb-1 text-xl font-semibold text-white">Hypothesis Chat</h3>
        <p className="text-sm text-white/85">
          Throw any hypothesis at me — scientific, philosophical, or completely wild. I&apos;ll engage
          with it seriously, creatively, and honestly.
        </p>
      </div>

      {history.length === 0 && (
        <>
          <p className="mb-2.5 text-xs font-bold tracking-wider text-text-muted uppercase">
            Try one of these
          </p>
          <div className="mb-6 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {STARTER_HYPOTHESES.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-lg border border-border-strong px-4 py-3 text-left text-sm text-text-primary transition-colors hover:bg-bg-card-alt"
              >
                {s}
              </button>
            ))}
          </div>
        </>
      )}

      <div className="flex-1 space-y-3">
        {history.map((m, i) => (
          <div
            key={i}
            className={`rounded-xl border border-border px-4 py-3 text-sm leading-relaxed ${
              m.role === "user" ? "bg-bg-card-alt text-text-primary" : "bg-bg-card text-text-secondary"
            }`}
          >
            {m.content}
          </div>
        ))}
        {sending && <div className="text-sm text-text-muted">Thinking…</div>}
      </div>

      <div className="mt-6 flex gap-2.5">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Type any hypothesis, however wild…"
          className="flex-1 rounded-full border border-border-strong bg-bg-card px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
        />
        <button
          onClick={() => send(input)}
          disabled={sending || !input.trim()}
          className="rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
        >
          ↑
        </button>
      </div>
    </div>
  );
}
