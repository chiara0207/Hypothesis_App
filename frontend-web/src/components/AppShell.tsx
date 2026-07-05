"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { BarChart3, Bell, Settings, Upload as UploadIcon, X } from "lucide-react";
import { NAV_ITEMS } from "@/lib/nav";
import { apiUpload, ApiError } from "@/lib/api";
import { useAppStore } from "@/lib/store";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [search, setSearch] = useState("");

  function submitSearch() {
    if (!search.trim()) return;
    router.push(`/find?q=${encodeURIComponent(search.trim())}`);
  }

  return (
    <div className="flex min-h-screen">
      {/* ── Sidebar ── */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-bg-sidebar px-4 pt-5 pb-4">
        <Link
          href="/"
          className="mb-5 flex items-center gap-2.5 border-b border-border pb-4 transition-opacity hover:opacity-80"
        >
          <div className="flex h-[34px] w-[34px] items-center justify-center rounded-[9px] bg-accent-soft text-base">
            <BarChart3 size={18} className="text-accent-hover" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-bold text-text-primary">Hypothesis</div>
            <div className="text-[0.78rem] text-text-secondary">Testing Assistant</div>
          </div>
        </Link>

        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href || pathname?.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                  active
                    ? "bg-accent-soft font-semibold text-accent-hover"
                    : "text-[#c7cddb] hover:bg-[#1a2030]"
                }`}
              >
                <Icon size={16} className={active ? "text-accent-hover" : "text-[#8b93a7]"} />
                <span>{item.label}</span>
                {!item.implemented && (
                  <span className="ml-auto rounded-full border border-border-strong px-1.5 py-0.5 text-[0.62rem] text-text-muted">
                    soon
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        <p className="mt-5 mb-2 ml-1 text-[0.72rem] font-bold tracking-wider text-text-muted uppercase">
          Upload
        </p>
        <div className="flex flex-col gap-2">
          <PdfUploadTile />
          <CsvUploadTile />
        </div>

        <div className="mt-auto flex items-center gap-2.5 border-t border-border pt-3.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-bold text-white">
            C
          </div>
          <div className="min-w-0 leading-tight">
            <div className="text-sm font-semibold text-text-primary">Chiara von Watzdorf</div>
            <div className="truncate text-[0.74rem] text-text-muted">chiara.vonwatzdorf@gmail.com</div>
          </div>
        </div>
      </aside>

      {/* ── Main column ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-border px-8 py-3.5">
          <div className="relative flex-1">
            <span className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-text-muted">
              🔍
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitSearch()}
              placeholder="Search papers, datasets, or ask a question…"
              className="w-full rounded-full border border-border-strong bg-bg-card py-2.5 pr-4 pl-10 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <Bell size={18} className="text-[#c9a227]" />
          <Settings size={18} className="text-text-secondary" />
        </div>
        <main className="mx-auto w-full max-w-5xl flex-1 px-8 py-6">{children}</main>
      </div>
    </div>
  );
}

function PdfUploadTile() {
  const { pdfUploaded, pdfFilename, setPdfUploaded, removePdf } = useAppStore();
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setStatus("loading");
    setError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await apiUpload<{ success: boolean; chunks_created: number; message: string }>(
        "/upload/pdf",
        formData,
      );
      if (res.success) {
        setPdfUploaded(file.name);
        setStatus("idle");
      } else {
        setError(res.message || "Upload failed");
        setStatus("error");
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
      setStatus("error");
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-border-strong bg-bg-card px-3 py-2.5">
      <p className="mb-1.5 text-[0.82rem] text-text-secondary">
        📄 Research PDF <em className="text-text-muted not-italic">(optional · max 200MB)</em>
      </p>
      {pdfUploaded ? (
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-text-primary" title={pdfFilename}>
            ✅ {pdfFilename}
          </span>
          <button
            onClick={removePdf}
            className="shrink-0 text-text-muted hover:text-danger-text"
            title="Remove PDF"
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
          <button
            onClick={() => inputRef.current?.click()}
            disabled={status === "loading"}
            className="flex items-center gap-1.5 rounded-md border border-border-strong px-2.5 py-1 text-xs text-text-primary hover:bg-bg-card-alt disabled:opacity-50"
          >
            <UploadIcon size={12} /> {status === "loading" ? "Uploading…" : "Upload"}
          </button>
          {status === "error" && <p className="mt-1 text-[0.7rem] text-danger-text">{error}</p>}
        </>
      )}
    </div>
  );
}

function CsvUploadTile() {
  const { csvSessionId, csvFilename, csvRows, csvColumns, setCsvSession, removeCsvSession } = useAppStore();
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  type CsvUploadResponse = {
    success: boolean;
    session_id: string;
    filename: string;
    rows: number;
    columns: string[];
    dtypes: Record<string, string>;
    preview: Record<string, string>[];
    message: string;
  };

  async function handleFile(file: File) {
    setStatus("loading");
    setError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await apiUpload<CsvUploadResponse>("/upload/csv", formData);
      if (res.success) {
        setCsvSession({
          sessionId: res.session_id,
          filename: res.filename,
          columns: res.columns,
          dtypes: res.dtypes,
          preview: res.preview,
          rows: res.rows,
        });
        setStatus("idle");
      } else {
        setError(res.message || "Upload failed");
        setStatus("error");
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
      setStatus("error");
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-border-strong bg-bg-card px-3 py-2.5">
      <p className="mb-1.5 text-[0.82rem] text-text-secondary">
        📊 Dataset <em className="text-text-muted not-italic">(CSV / XLSX)</em>
      </p>
      {csvSessionId ? (
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-text-primary" title={csvFilename}>
            ✅ {csvFilename} · {csvRows}r × {csvColumns.length}c
          </span>
          <button
            onClick={removeCsvSession}
            className="shrink-0 text-text-muted hover:text-danger-text"
            title="Remove dataset"
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
          <button
            onClick={() => inputRef.current?.click()}
            disabled={status === "loading"}
            className="flex items-center gap-1.5 rounded-md border border-border-strong px-2.5 py-1 text-xs text-text-primary hover:bg-bg-card-alt disabled:opacity-50"
          >
            <UploadIcon size={12} /> {status === "loading" ? "Uploading…" : "Upload"}
          </button>
          {status === "error" && <p className="mt-1 text-[0.7rem] text-danger-text">{error}</p>}
        </>
      )}
    </div>
  );
}
