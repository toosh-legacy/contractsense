"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  AssessmentResponse,
  HiddenClause,
  Industry,
  ScoreDetail,
} from "@/lib/types";
import { Button, ErrorBanner, RiskBadge, Spinner } from "./ui";

/**
 * Risk is a status: low is good, high is bad. So it uses the same
 * red / amber / emerald tokens as the rest of the app.
 */
const RISK_METER: Record<string, { fill: string; text: string; label: string }> = {
  LOW: { fill: "bg-emerald-500", text: "text-emerald-300", label: "Low risk" },
  MODERATE: { fill: "bg-amber-500", text: "text-amber-300", label: "Moderate risk" },
  HIGH: { fill: "bg-red-500", text: "text-red-300", label: "High risk" },
};

/**
 * Margin is not a status — a tight contract isn't an error, it just has
 * less room. So it uses one accent hue that gets stronger as the score
 * rises, rather than the red/green ramp. That also stops the two meters
 * contradicting each other, where high means bad on one and good on the
 * other.
 */
const MARGIN_METER: Record<string, { fill: string; text: string; label: string }> = {
  UNKNOWN: { fill: "bg-gray-600", text: "text-gray-400", label: "Not assessed" },
  TIGHT: { fill: "bg-indigo-500/40", text: "text-indigo-300", label: "Little room" },
  SOME_ROOM: { fill: "bg-indigo-500/70", text: "text-indigo-300", label: "Some room" },
  STRONG_LEVERAGE: { fill: "bg-indigo-400", text: "text-indigo-200", label: "Strong leverage" },
};

export function ScorePanel({ collection }: { collection: string }) {
  const [result, setResult] = useState<AssessmentResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [industry, setIndustry] = useState<string>("");

  // Show a previous assessment straight away if there is one. A miss
  // here is the normal case, not an error, so it stays quiet.
  useEffect(() => {
    let cancelled = false;

    api
      .getAssessment(collection)
      .then((cached) => {
        if (cancelled) return;
        setResult(cached);
        setIndustry(cached.industry);
      })
      .catch(() => {});

    api
      .industries()
      .then((list) => !cancelled && setIndustries(list))
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [collection]);

  async function run(refresh: boolean) {
    setError(null);
    setBusy(true);
    try {
      const assessment = await api.assess(
        collection,
        industry || undefined,
        refresh,
      );
      setResult(assessment);
      setIndustry(assessment.industry);
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
          Score this contract on risk and negotiating room
        </p>
        <p className="mx-auto mt-1 max-w-md text-sm text-gray-500">
          Every clause is checked for risky and hidden terms, then the
          commercial terms are compared against industry benchmarks and current
          market conditions. Long contracts take a while.
        </p>
        <div className="mt-6">
          <Button onClick={() => void run(false)} disabled={busy}>
            {busy && <Spinner />}
            {busy ? "Assessing contract…" : "Run assessment"}
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
      {/* Two meters. Each states its direction, because "high" means
          something different on each one. */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Meter
          title="Risk score"
          caption="Higher means riskier"
          detail={result.risk}
          styles={RISK_METER}
        />
        <Meter
          title="Margin meter"
          caption="Higher means more room to negotiate"
          detail={result.margin}
          styles={MARGIN_METER}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-white/10 pt-5">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-gray-200">{result.contract_type}</p>
          <p className="mt-0.5 text-xs text-gray-500">
            Benchmarked against {result.industry_display_name} ·{" "}
            {result.total_clauses_analyzed} clauses analysed
            {result.cached && " · cached"}
          </p>
        </div>
        <label className="sr-only" htmlFor="industry">
          Industry
        </label>
        <select
          id="industry"
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          className="rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-400"
        >
          {industries.map((i) => (
            <option key={i.key} value={i.key}>
              {i.display_name}
            </option>
          ))}
        </select>
        <Button variant="ghost" onClick={() => void run(true)} disabled={busy}>
          {busy && <Spinner />}
          {busy ? "Re-running…" : "Re-run"}
        </Button>
      </div>

      {error && <ErrorBanner message={error} />}

      <section>
        <h3 className="text-sm font-medium text-gray-200">
          Hidden clauses{" "}
          <span className="text-gray-500">({result.hidden_clauses.length})</span>
        </h3>
        <p className="mt-1 text-xs text-gray-500">
          Terms that are easy to miss on a read-through and expensive to
          discover later.
        </p>

        <div className="mt-4 space-y-3">
          {result.hidden_clauses.map((clause, i) => (
            <HiddenClauseCard key={`${clause.type}-${i}`} clause={clause} />
          ))}
          {result.hidden_clauses.length === 0 && (
            <p className="py-6 text-center text-sm text-gray-500">
              No hidden clauses detected in this contract.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

/**
 * A score against a fixed 0-100 limit — a meter, not a chart. The track
 * is recessive, the fill is thin, and the drivers underneath say why the
 * number is what it is, so nobody has to take the score on faith.
 */
function Meter({
  title,
  caption,
  detail,
  styles,
}: {
  title: string;
  caption: string;
  detail: ScoreDetail;
  styles: Record<string, { fill: string; text: string; label: string }>;
}) {
  const style = styles[detail.band] ?? styles.UNKNOWN ?? styles.MODERATE;

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-xs tracking-wide text-gray-500 uppercase">{title}</p>
        <p className={`text-xs font-semibold ${style.text}`}>{style.label}</p>
      </div>

      <p className="mt-2 text-5xl leading-none font-semibold text-gray-50">
        {detail.score}
        <span className="ml-1 text-base font-normal text-gray-600">/ 100</span>
      </p>

      <div
        role="meter"
        aria-valuenow={detail.score}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${title}: ${detail.score} of 100, ${style.label}`}
        className="mt-4 h-2 overflow-hidden rounded-full bg-white/5"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${style.fill}`}
          style={{ width: `${detail.score}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-gray-600">{caption}</p>

      <ul className="mt-4 space-y-1.5 border-t border-white/10 pt-4">
        {detail.drivers.map((driver, i) => (
          <li key={i} className="flex gap-2 text-xs leading-relaxed text-gray-400">
            <span className="text-gray-600">•</span>
            <span>{driver}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function HiddenClauseCard({ clause }: { clause: HiddenClause }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
      <div className="flex items-start gap-3">
        <RiskBadge level={clause.severity} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-gray-200 capitalize">
            {clause.type.replace(/_/g, " ")}
            <span className="ml-2 text-xs font-normal text-gray-500">
              page {clause.page_num}
            </span>
          </p>
          {clause.quote && (
            <p className="mt-2 rounded-md bg-black/30 px-3 py-2 text-xs leading-relaxed text-gray-400 italic">
              “{clause.quote}”
            </p>
          )}
          <p className="mt-2 text-sm leading-relaxed text-gray-300">
            {clause.why_it_matters}
          </p>
        </div>
      </div>
    </div>
  );
}
