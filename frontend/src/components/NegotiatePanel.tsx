"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  AssessmentResponse,
  LeverPosition,
  NegotiationLever,
} from "@/lib/types";
import { Button, ErrorBanner, Spinner } from "./ui";

/**
 * Where a term sits against the market, from the buyer's point of view.
 * These are status labels, so each one ships with its own words — the
 * colour is never the only thing carrying the meaning.
 */
const POSITIONS: Record<LeverPosition, { label: string; style: string }> = {
  worse_than_market: {
    label: "Below market",
    style: "border-red-500/40 bg-red-500/15 text-red-300",
  },
  slightly_worse: {
    label: "Slightly below",
    style: "border-amber-500/40 bg-amber-500/15 text-amber-300",
  },
  not_addressed: {
    label: "Not addressed",
    style: "border-indigo-400/40 bg-indigo-500/15 text-indigo-200",
  },
  at_market: {
    label: "At market",
    style: "border-white/15 bg-white/5 text-gray-400",
  },
  better_than_market: {
    label: "Above market",
    style: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
  },
};

export function NegotiatePanel({ collection }: { collection: string }) {
  const [result, setResult] = useState<AssessmentResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Levers come from the assessment, so reuse it rather than recomputing
  useEffect(() => {
    let cancelled = false;

    api
      .getAssessment(collection)
      .then((cached) => !cancelled && setResult(cached))
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [collection]);

  async function run() {
    setError(null);
    setBusy(true);
    try {
      setResult(await api.assess(collection));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Assessment failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!result) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-gray-300">
          Find where you can push back on this contract
        </p>
        <p className="mx-auto mt-1 max-w-md text-sm text-gray-500">
          Each commercial term is compared against industry benchmarks and
          current market conditions, then turned into something you can ask for.
        </p>
        <div className="mt-6">
          <Button onClick={() => void run()} disabled={busy}>
            {busy && <Spinner />}
            {busy ? "Assessing contract…" : "Find negotiation levers"}
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

  return (
    <div className="animate-rise space-y-6">
      {result.market_summary && (
        <section className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
          <p className="text-xs tracking-wide text-gray-500 uppercase">
            Market context
          </p>
          <p className="mt-2 text-sm leading-relaxed text-gray-300">
            {result.market_summary}
          </p>

          {result.market_trends.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {result.market_trends.map((trend, i) => (
                <li
                  key={i}
                  className="flex gap-2 text-sm leading-relaxed text-gray-400"
                >
                  <span className="text-gray-600">•</span>
                  <span>{trend}</span>
                </li>
              ))}
            </ul>
          )}

          {result.market_sources.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2 border-t border-white/10 pt-3">
              {result.market_sources.map((source) => (
                <a
                  key={source.url}
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="max-w-xs truncate rounded-full border border-white/15 px-3 py-1 text-xs text-gray-400 transition hover:border-indigo-400/50 hover:text-indigo-200"
                >
                  {source.title}
                </a>
              ))}
            </div>
          )}
        </section>
      )}

      <div className="space-y-3">
        {result.levers.map((lever) => (
          <LeverCard key={lever.benchmark_key} lever={lever} />
        ))}
        {result.levers.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-500">
            No commercial terms were found to benchmark in this contract.
          </p>
        )}
      </div>
    </div>
  );
}

function LeverCard({ lever }: { lever: NegotiationLever }) {
  const position = POSITIONS[lever.position] ?? POSITIONS.at_market;

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 transition hover:border-white/20">
      <div className="flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 text-sm font-medium text-gray-200">
          {lever.label}
        </p>
        <span className="text-[11px] tracking-wide text-gray-600 uppercase">
          {lever.estimated_impact} impact
        </span>
        <span
          className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold tracking-wide uppercase ${position.style}`}
        >
          {position.label}
        </span>
      </div>

      {/* This contract vs the market, side by side — the comparison is
          the whole point, so it should not need reading two paragraphs */}
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg bg-black/30 px-3 py-2">
          <p className="text-[11px] tracking-wide text-gray-600 uppercase">
            This contract
          </p>
          <p className="mt-1 text-xs leading-relaxed text-gray-300">
            {lever.contract_position}
          </p>
        </div>
        <div className="rounded-lg bg-black/30 px-3 py-2">
          <p className="text-[11px] tracking-wide text-gray-600 uppercase">
            Market norm
          </p>
          <p className="mt-1 text-xs leading-relaxed text-gray-300">
            {lever.market_norm}
          </p>
        </div>
      </div>

      {lever.ask && (
        <div className="mt-3 rounded-lg border border-indigo-400/30 bg-indigo-500/10 px-3 py-2">
          <p className="text-[11px] tracking-wide text-indigo-300/70 uppercase">
            Ask for
          </p>
          <p className="mt-1 text-sm leading-relaxed text-indigo-100">
            {lever.ask}
          </p>
        </div>
      )}

      {lever.rationale && (
        <p className="mt-2 text-xs leading-relaxed text-gray-500">
          {lever.rationale}
        </p>
      )}
    </div>
  );
}
