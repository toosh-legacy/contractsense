"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { KeyTermsResponse } from "@/lib/types";
import { Button, ErrorBanner, Spinner } from "./ui";

export function TermsPanel({ file }: { file: File }) {
  const [terms, setTerms] = useState<KeyTermsResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    setBusy(true);
    try {
      setTerms(await api.extract(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!terms) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-gray-300">Pull out the structured facts</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-gray-500">
          Contract type, parties, effective and expiry dates, governing law and
          key obligations.
        </p>
        <div className="mt-6">
          <Button onClick={() => void run()} disabled={busy}>
            {busy && <Spinner />}
            {busy ? "Extracting…" : "Extract key terms"}
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
      <div className="flex items-center gap-3">
        <span className="rounded-full border border-indigo-400/40 bg-indigo-500/15 px-3 py-1 text-sm font-medium text-indigo-200">
          {terms.contract_type}
        </span>
        <span className="truncate text-sm text-gray-500">{terms.filename}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Effective date" value={terms.effective_date} />
        <Field label="Expiry date" value={terms.expiry_date} />
        <Field label="Governing law" value={terms.governing_law} />
      </div>

      <section>
        <h3 className="text-xs tracking-wide text-gray-500 uppercase">
          Parties
        </h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {terms.parties.length > 0 ? (
            terms.parties.map((p) => (
              <span
                key={p}
                className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-gray-200"
              >
                {p}
              </span>
            ))
          ) : (
            <span className="text-sm text-gray-600">None identified</span>
          )}
        </div>
      </section>

      <section>
        <h3 className="text-xs tracking-wide text-gray-500 uppercase">
          Key obligations
        </h3>
        <ol className="mt-2 space-y-2">
          {terms.key_obligations.length > 0 ? (
            terms.key_obligations.map((o, i) => (
              <li
                key={i}
                className="flex gap-3 rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3 text-sm leading-relaxed text-gray-300"
              >
                <span className="text-gray-600">{i + 1}.</span>
                <span>{o}</span>
              </li>
            ))
          ) : (
            <li className="text-sm text-gray-600">None identified</li>
          )}
        </ol>
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3">
      <p className="text-xs tracking-wide text-gray-500 uppercase">{label}</p>
      <p
        className={`mt-1 text-sm ${value ? "text-gray-100" : "text-gray-600 italic"}`}
      >
        {value ?? "Not specified"}
      </p>
    </div>
  );
}
