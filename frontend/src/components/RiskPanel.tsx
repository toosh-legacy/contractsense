"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { ClauseAnalysis, RiskLevel, RiskReport } from "@/lib/types";
import { Button, ErrorBanner, RiskBadge, Spinner, Stat } from "./ui";

const FILTERS: Array<RiskLevel | "ALL"> = ["ALL", "HIGH", "MEDIUM", "LOW"];

const BAR_COLORS: Record<RiskLevel, string> = {
  HIGH: "bg-red-500",
  MEDIUM: "bg-amber-500",
  LOW: "bg-emerald-500",
};

export function RiskPanel({ file }: { file: File }) {
  const [report, setReport] = useState<RiskReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<RiskLevel | "ALL">("ALL");

  async function run() {
    setError(null);
    setBusy(true);
    try {
      setReport(await api.analyze(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!report) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-gray-300">
          Score every clause LOW / MEDIUM / HIGH
        </p>
        <p className="mx-auto mt-1 max-w-md text-sm text-gray-500">
          Each clause is sent to the model with a reason and a recommendation.
          Long contracts take a while.
        </p>
        <div className="mt-6">
          <Button onClick={() => void run()} disabled={busy}>
            {busy && <Spinner />}
            {busy ? "Analyzing clauses…" : "Run risk analysis"}
          </Button>
        </div>
        {error && (
          <div className="mx-auto mt-5 max-w-lg">
            <ErrorBanner message={error} />
          </div>
        )}
      </div>
    );
  }

  const total = report.total_clauses_analyzed || 1;
  const shown =
    filter === "ALL"
      ? report.all_clauses
      : report.all_clauses.filter((c) => c.risk_level === filter);

  return (
    <div className="animate-rise space-y-6">
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3">
          <p className="text-xs tracking-wide text-gray-500 uppercase">
            Overall risk
          </p>
          <div className="mt-2">
            <RiskBadge level={report.overall_risk} size="lg" />
          </div>
        </div>
        <Stat label="Clauses" value={report.total_clauses_analyzed} />
        <Stat label="High risk" value={report.risk_counts.HIGH ?? 0} />
        <Stat label="Medium risk" value={report.risk_counts.MEDIUM ?? 0} />
      </div>

      {/* Distribution bar */}
      <div className="flex h-2.5 overflow-hidden rounded-full bg-white/5">
        {(["HIGH", "MEDIUM", "LOW"] as RiskLevel[]).map((level) => {
          const pct = ((report.risk_counts[level] ?? 0) / total) * 100;
          if (pct === 0) return null;
          return (
            <div
              key={level}
              className={BAR_COLORS[level]}
              style={{ width: `${pct}%` }}
              title={`${level}: ${report.risk_counts[level]}`}
            />
          );
        })}
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => {
          const count =
            f === "ALL" ? report.all_clauses.length : (report.risk_counts[f] ?? 0);
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                filter === f
                  ? "border-indigo-400 bg-indigo-500/15 text-indigo-200"
                  : "border-white/15 text-gray-400 hover:bg-white/5"
              }`}
            >
              {f} ({count})
            </button>
          );
        })}
      </div>

      <div className="space-y-3">
        {shown.map((clause) => (
          <ClauseCard key={clause.chunk_id} clause={clause} />
        ))}
        {shown.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-500">
            No {filter.toLowerCase()} risk clauses found.
          </p>
        )}
      </div>
    </div>
  );
}

function ClauseCard({ clause }: { clause: ClauseAnalysis }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] transition hover:border-white/20">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left"
      >
        <RiskBadge level={clause.risk_level} />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-gray-200 capitalize">
            {clause.clause_type.replace(/_/g, " ")}
            <span className="ml-2 text-xs font-normal text-gray-500">
              page {clause.page_num}
            </span>
          </span>
          <span className="mt-1 block truncate text-xs text-gray-500">
            {clause.text_preview}
          </span>
        </span>
        <span className="text-gray-600">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="animate-rise space-y-3 border-t border-white/10 px-4 py-4 text-sm">
          <p className="rounded-md bg-black/30 px-3 py-2 text-xs leading-relaxed text-gray-400">
            {clause.text_preview}
          </p>
          <div>
            <p className="text-xs tracking-wide text-gray-500 uppercase">
              Why it matters
            </p>
            <p className="mt-1 leading-relaxed text-gray-300">{clause.reason}</p>
          </div>
          {clause.recommendation && (
            <div>
              <p className="text-xs tracking-wide text-gray-500 uppercase">
                Recommendation
              </p>
              <p className="mt-1 leading-relaxed text-indigo-200">
                {clause.recommendation}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
