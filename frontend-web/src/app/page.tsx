import Link from "next/link";
import { ArrowRight, BarChart3 } from "lucide-react";
import { NAV_ITEMS } from "@/lib/nav";

const STEPS = [
  {
    title: "Upload",
    body: "Bring a dataset (CSV/XLSX) and/or a research PDF in the sidebar.",
  },
  {
    title: "Ask",
    body: "Describe your hypothesis in plain language — no need to name a statistical test.",
  },
  {
    title: "Understand",
    body: "Get the right test run automatically, explained in both technical and plain terms.",
  },
];

export default function LandingPage() {
  return (
    <div>
      <div className="mb-8 rounded-2xl border border-border-strong bg-gradient-to-br from-[#1a2340] to-[#24305a] p-8">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-white/10">
          <BarChart3 size={26} className="text-white" />
        </div>
        <h1 className="mb-3 text-3xl font-bold text-white">Hypothesis Testing Assistant</h1>
        <p className="max-w-2xl text-[0.95rem] leading-relaxed text-white/85">
          An AI-assisted workspace for the full lifecycle of testing a research hypothesis: find
          supporting literature and open datasets, run the right statistical test automatically,
          understand the result in plain language, and interrogate a source PDF directly — all in one
          place.
        </p>
        <Link
          href="/statistical-analysis"
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-white hover:bg-accent-hover"
        >
          Get started <ArrowRight size={15} />
        </Link>
      </div>

      <p className="mb-3 text-xs font-bold tracking-wider text-text-muted uppercase">How it works</p>
      <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {STEPS.map((s, i) => (
          <div key={s.title} className="rounded-xl border border-border bg-bg-card p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent-hover">
                {i + 1}
              </span>
              <p className="text-sm font-semibold text-text-primary">{s.title}</p>
            </div>
            <p className="text-[0.85rem] leading-relaxed text-text-secondary">{s.body}</p>
          </div>
        ))}
      </div>

      <p className="mb-3 text-xs font-bold tracking-wider text-text-muted uppercase">
        What you can do here
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className="group flex items-start gap-3 rounded-xl border border-border bg-bg-card p-4 transition-colors hover:border-border-strong hover:bg-bg-card-alt"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft">
                <Icon size={17} className="text-accent-hover" />
              </span>
              <span className="min-w-0">
                <span className="flex items-center gap-1.5 text-sm font-semibold text-text-primary">
                  {item.label}
                  <ArrowRight
                    size={13}
                    className="text-text-muted opacity-0 transition-opacity group-hover:opacity-100"
                  />
                </span>
                <span className="mt-1 block text-[0.85rem] leading-relaxed text-text-secondary">
                  {item.description}
                </span>
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
