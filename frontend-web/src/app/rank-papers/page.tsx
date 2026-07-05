"use client";

import { useRef, useState } from "react";
import { apiUpload, ApiError } from "@/lib/api";

type RankedPaper = {
  filename: string;
  score: number;
  label: string;
  explanation: string;
  key_quote: string;
};

const LABEL_COLORS: Record<string, { bg: string; fg: string; border: string }> = {
  "Highly Relevant": { bg: "#e6f4ec", fg: "#0a7c42", border: "#b8e6cc" },
  Relevant: { bg: "#e8f0fb", fg: "#1a56a0", border: "#b8d0f0" },
  "Somewhat Relevant": { bg: "#fef6e8", fg: "#a05c00", border: "#f0d9a8" },
  "Less Relevant": { bg: "#fdecea", fg: "#c0392b", border: "#f5c6c0" },
};

export default function RankPapersPage() {
  const [question, setQuestion] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [papers, setPapers] = useState<RankedPaper[] | null>(null);
  const [rankedQuestion, setRankedQuestion] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function addFiles(newFiles: FileList) {
    setFiles((f) => [...f, ...Array.from(newFiles)].slice(0, 20));
  }

  function removeFile(idx: number) {
    setFiles((f) => f.filter((_, i) => i !== idx));
  }

  async function rank() {
    if (!question.trim() || files.length === 0) return;
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("question", question);
      files.forEach((f) => formData.append("files", f));
      const res = await apiUpload<{ question: string; papers: RankedPaper[] }>(
        "/rank/papers",
        formData,
      );
      setPapers(res.papers);
      setRankedQuestion(res.question);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ranking failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="mb-6 rounded-2xl border border-border-strong bg-gradient-to-br from-[#1a2340] to-[#24305a] p-5">
        <h3 className="mb-1 text-xl font-semibold text-white">Paper Relevance Ranker</h3>
        <p className="text-sm text-white/85">
          Upload your collected PDFs and enter your research question. The AI ranks every paper by how
          well it fits your thesis and explains why.
        </p>
      </div>

      <div className="mb-6 rounded-xl border border-border bg-bg-card p-5">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. How does social media use affect mental health in adolescents?"
          rows={3}
          className="mb-4 w-full resize-y rounded-lg border border-border-strong bg-bg-app px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
        />

        <p className="mb-2 text-sm text-text-secondary">Upload research PDFs (up to 20)</p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          multiple
          className="hidden"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
        <div className="mb-3 flex items-center gap-3">
          <button
            onClick={() => inputRef.current?.click()}
            className="rounded-md border border-border-strong px-3.5 py-2 text-sm text-text-primary hover:bg-bg-card-alt"
          >
            Upload
          </button>
          <span className="text-xs text-text-muted">200MB per file · PDF</span>
        </div>

        {files.length > 0 && (
          <ul className="mb-4 space-y-1.5">
            {files.map((f, i) => (
              <li
                key={i}
                className="flex items-center justify-between rounded-md border border-border bg-bg-card-alt px-3 py-1.5 text-sm text-text-secondary"
              >
                <span className="truncate">{f.name}</span>
                <button onClick={() => removeFile(i)} className="ml-2 shrink-0 text-text-muted hover:text-danger-text">
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}

        <button
          onClick={rank}
          disabled={loading || !question.trim() || files.length === 0}
          className="rounded-lg bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? `Analysing ${files.length} paper(s)…` : "Rank Papers"}
        </button>
      </div>

      {error && (
        <div className="mb-5 rounded-lg border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger-text">
          {error}
        </div>
      )}

      {papers && (
        <>
          <p className="mb-3 text-sm text-text-secondary">
            Ranked {papers.length} paper(s) for:{" "}
            <span className="font-semibold text-text-primary">{rankedQuestion}</span>
          </p>
          <div className="space-y-2.5">
            {papers.map((p, i) => {
              const colors = LABEL_COLORS[p.label] ?? { bg: "#333", fg: "#eee", border: "#555" };
              const pct = Math.round(p.score * 100);
              return (
                <details
                  key={i}
                  open={i < 3}
                  className="rounded-lg border border-border bg-bg-card px-4 py-3"
                >
                  <summary className="cursor-pointer text-sm font-semibold text-text-primary">
                    {i + 1}. {p.filename}
                  </summary>
                  <div className="mt-3 border-t border-border pt-3">
                    <div className="mb-3 flex flex-wrap items-center gap-3">
                      <span
                        className="rounded-full border px-3 py-1 text-xs font-bold"
                        style={{ background: colors.bg, color: colors.fg, borderColor: colors.border }}
                      >
                        {p.label}
                      </span>
                      <div className="h-2 max-w-[200px] flex-1 overflow-hidden rounded-full bg-border">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-accent to-accent-hover"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-sm font-semibold text-accent-hover">{pct}% match</span>
                    </div>
                    <p className="mb-2.5 text-sm leading-relaxed text-text-secondary">{p.explanation}</p>
                    {p.key_quote !== "—" && (
                      <div className="rounded-r-md border-l-4 border-accent bg-bg-card-alt px-3.5 py-2.5 text-sm text-text-secondary italic">
                        &quot;{p.key_quote}&quot;
                      </div>
                    )}
                  </div>
                </details>
              );
            })}
          </div>
          <p className="mt-4 text-xs text-text-muted">
            Word/PDF report export isn&apos;t wired up yet in this rebuild — available in the Streamlit
            version for now.
          </p>
        </>
      )}
    </div>
  );
}
