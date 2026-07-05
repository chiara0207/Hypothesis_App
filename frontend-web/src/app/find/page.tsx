"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiPost, ApiError } from "@/lib/api";

type PaperResult = {
  title: string;
  authors: string[];
  abstract: string | null;
  year: number | null;
  citation_count: number | null;
  doi: string | null;
  pdf_url: string | null;
  paper_url: string | null;
  source: string;
};

type DatasetResult = {
  title: string;
  description: string | null;
  authors: string[];
  year: number | null;
  doi: string | null;
  dataset_url: string | null;
  file_formats: string[];
  source: string;
};

const PAPER_SOURCES = ["Semantic Scholar", "arXiv", "PubMed", "OpenAlex"];
const DATASET_SOURCES = ["Zenodo", "DataCite", "OpenAlex Datasets"];

const SOURCE_COLORS: Record<string, string> = {
  "Semantic Scholar": "#2d6a9f",
  arXiv: "#b31b1b",
  PubMed: "#2e7d32",
  OpenAlex: "#6a1b9a",
  Zenodo: "#1457a8",
  DataCite: "#00a19a",
  "OpenAlex Datasets": "#6a1b9a",
};

export default function FindPage() {
  return (
    <Suspense fallback={null}>
      <FindPageContent />
    </Suspense>
  );
}

function FindPageContent() {
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<"papers" | "datasets">("papers");
  const [question, setQuestion] = useState(() => searchParams.get("q") ?? "");
  const [limit, setLimit] = useState(10);
  const [sources, setSources] = useState<string[]>(PAPER_SOURCES);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [queryUsed, setQueryUsed] = useState("");
  const [summary, setSummary] = useState("");
  const [paperResults, setPaperResults] = useState<PaperResult[] | null>(null);
  const [datasetResults, setDatasetResults] = useState<DatasetResult[] | null>(null);

  function switchMode(next: "papers" | "datasets") {
    setMode(next);
    setSources(next === "papers" ? PAPER_SOURCES : DATASET_SOURCES);
  }

  function toggleSource(src: string) {
    setSources((s) => (s.includes(src) ? s.filter((x) => x !== src) : [...s, src]));
  }

  async function search() {
    if (!question.trim() || sources.length === 0) return;
    setLoading(true);
    setError("");
    try {
      if (mode === "papers") {
        const res = await apiPost<{ query_used: string; results: PaperResult[]; summary: string }>(
          "/search/papers",
          { question, limit, sources },
        );
        setQueryUsed(res.query_used);
        setSummary(res.summary);
        setPaperResults(res.results);
        setDatasetResults(null);
      } else {
        const res = await apiPost<{ query_used: string; results: DatasetResult[]; summary: string }>(
          "/search/datasets",
          { question, limit, sources },
        );
        setQueryUsed(res.query_used);
        setSummary(res.summary);
        setDatasetResults(res.results);
        setPaperResults(null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  const results = mode === "papers" ? paperResults : datasetResults;

  return (
    <div>
      <div className="mb-6 rounded-2xl border border-border-strong bg-gradient-to-br from-[#1a2340] to-[#24305a] p-5">
        <h3 className="mb-1 text-xl font-semibold text-white">Find Papers &amp; Datasets</h3>
        <p className="text-sm text-white/85">
          Enter your hypothesis or research question — the AI extracts keywords and searches academic
          literature or open dataset registries for the most relevant matches.
        </p>
      </div>

      <p className="mb-2 text-sm font-semibold text-text-primary">What are you looking for?</p>
      <div className="mb-4 flex gap-4">
        {(["papers", "datasets"] as const).map((m) => (
          <label key={m} className="flex cursor-pointer items-center gap-2 text-sm text-text-primary">
            <input type="radio" checked={mode === m} onChange={() => switchMode(m)} className="accent-accent" />
            {m === "papers" ? "Research Papers" : "Datasets"}
          </label>
        ))}
      </div>

      <div className="mb-6 rounded-xl border border-border bg-bg-card p-5">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Does sleep deprivation impair working memory in young adults?"
          rows={3}
          className="mb-4 w-full resize-y rounded-lg border border-border-strong bg-bg-app px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
        />

        <div className="mb-4 flex items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-text-secondary">Results to return</label>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded-lg border border-border-strong bg-bg-app px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
            >
              {[5, 10, 15, 20].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={search}
            disabled={loading || !question.trim() || sources.length === 0}
            className="rounded-lg bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Searching…" : mode === "papers" ? "Search Papers" : "Search Datasets"}
          </button>
        </div>

        <p className="mb-2 text-xs font-bold tracking-wider text-text-muted uppercase">Sources</p>
        <div className="flex flex-wrap gap-4">
          {(mode === "papers" ? PAPER_SOURCES : DATASET_SOURCES).map((src) => (
            <label key={src} className="flex cursor-pointer items-center gap-2 text-sm text-text-primary">
              <input
                type="checkbox"
                checked={sources.includes(src)}
                onChange={() => toggleSource(src)}
                className="accent-accent"
              />
              {src}
            </label>
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-5 rounded-lg border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger-text">
          {error}
        </div>
      )}

      {results && (
        <>
          <p className="mb-3 text-sm text-text-secondary">
            Search query: <span className="font-semibold text-text-primary">{queryUsed}</span> ·{" "}
            {results.length} result{results.length !== 1 ? "s" : ""} returned
          </p>

          {summary && (
            <div className="mb-4 rounded-lg border border-border border-l-4 border-l-accent bg-bg-card-alt px-4 py-4">
              <p className="mb-1.5 font-semibold text-text-primary">
                {mode === "papers" ? "Literature summary" : "Dataset fit summary"}
              </p>
              <p className="text-sm leading-relaxed text-text-secondary">{summary}</p>
            </div>
          )}

          {results.length === 0 ? (
            <p className="text-sm text-text-muted">
              No {mode === "papers" ? "papers" : "datasets"} found. Try rephrasing your hypothesis.
            </p>
          ) : mode === "papers" ? (
            <div className="space-y-2.5">
              {(paperResults ?? []).map((p, i) => (
                <details
                  key={i}
                  open={i === 0}
                  className="rounded-lg border border-border bg-bg-card px-4 py-3"
                >
                  <summary className="cursor-pointer text-sm font-semibold text-text-primary">
                    {i + 1}. {p.title} {p.year ? `(${p.year})` : ""}
                  </summary>
                  <div className="mt-3 border-t border-border pt-3">
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
                      <span
                        className="rounded-full px-2.5 py-0.5 text-xs font-bold text-white"
                        style={{ background: SOURCE_COLORS[p.source] ?? "#555" }}
                      >
                        {p.source}
                      </span>
                      <span className="text-text-secondary">{p.authors.slice(0, 3).join(", ")}</span>
                      <span className="text-text-secondary">
                        🔖 {p.citation_count != null ? p.citation_count.toLocaleString() : "—"} citations
                      </span>
                    </div>
                    <p className="mb-2 text-[0.9rem] leading-relaxed text-text-secondary">
                      {p.abstract ? p.abstract.slice(0, 400) : "No abstract available."}
                    </p>
                    <div className="flex gap-3 text-sm">
                      {p.paper_url && (
                        <a href={p.paper_url} target="_blank" className="text-accent-hover hover:underline">
                          View source
                        </a>
                      )}
                      {p.pdf_url && (
                        <a href={p.pdf_url} target="_blank" className="text-accent-hover hover:underline">
                          Open PDF
                        </a>
                      )}
                      {p.doi && (
                        <a
                          href={`https://doi.org/${p.doi}`}
                          target="_blank"
                          className="text-accent-hover hover:underline"
                        >
                          DOI
                        </a>
                      )}
                    </div>
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <div className="space-y-2.5">
              {(datasetResults ?? []).map((d, i) => (
                <details
                  key={i}
                  open={i === 0}
                  className="rounded-lg border border-border bg-bg-card px-4 py-3"
                >
                  <summary className="cursor-pointer text-sm font-semibold text-text-primary">
                    {i + 1}. {d.title} {d.year ? `(${d.year})` : ""}
                  </summary>
                  <div className="mt-3 border-t border-border pt-3">
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
                      <span
                        className="rounded-full px-2.5 py-0.5 text-xs font-bold text-white"
                        style={{ background: SOURCE_COLORS[d.source] ?? "#555" }}
                      >
                        {d.source}
                      </span>
                      <span className="text-text-secondary">{d.authors.slice(0, 3).join(", ")}</span>
                    </div>
                    <p className="mb-2 text-[0.9rem] leading-relaxed text-text-secondary">
                      {d.description ? d.description.slice(0, 400) : "No description available."}
                    </p>
                    {d.file_formats.length > 0 && (
                      <div className="mb-2 flex gap-1.5">
                        {d.file_formats.map((f) => (
                          <span
                            key={f}
                            className="rounded-full border border-border-strong bg-bg-card-alt px-2 py-0.5 text-[0.7rem] font-semibold text-text-secondary"
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-3 text-sm">
                      {d.dataset_url && (
                        <a href={d.dataset_url} target="_blank" className="text-accent-hover hover:underline">
                          View dataset
                        </a>
                      )}
                      {d.doi && (
                        <a
                          href={`https://doi.org/${d.doi}`}
                          target="_blank"
                          className="text-accent-hover hover:underline"
                        >
                          DOI
                        </a>
                      )}
                    </div>
                  </div>
                </details>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
