"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { ChunkResult } from "@/lib/types";
import { Button, EmptyState, ErrorBanner, Spinner } from "./ui";

export function SearchPanel({ collection }: { collection: string }) {
  const [query, setQuery] = useState("");
  const [nResults, setNResults] = useState(5);
  const [results, setResults] = useState<ChunkResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!query.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const res = await api.search(collection, query, nResults);
      setResults(res.results);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed.");
      setResults(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
        className="flex flex-wrap gap-2"
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Semantic search — e.g. 'confidentiality obligations'"
          className="min-w-64 flex-1 rounded-lg border border-white/15 bg-black/30 px-4 py-2.5 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-indigo-400"
        />
        <select
          value={nResults}
          onChange={(e) => setNResults(Number(e.target.value))}
          className="rounded-lg border border-white/15 bg-black/30 px-3 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-400"
        >
          {[3, 5, 10, 20].map((n) => (
            <option key={n} value={n} className="bg-gray-900">
              {n} results
            </option>
          ))}
        </select>
        <Button type="submit" disabled={busy || !query.trim()}>
          {busy && <Spinner />}
          Search
        </Button>
      </form>

      {error && <ErrorBanner message={error} />}

      {!results && !error && (
        <EmptyState
          title="Search the raw clauses"
          hint="Returns the closest matching chunks with their similarity scores — no model generation involved."
        />
      )}

      {results?.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-500">
          No matching chunks.
        </p>
      )}

      <div className="space-y-3">
        {results?.map((r) => (
          <div
            key={`${r.page_num}-${r.chunk_index}`}
            className="animate-rise rounded-xl border border-white/10 bg-white/[0.02] p-4"
          >
            <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
              <span>
                page {r.page_num} · chunk {r.chunk_index}
              </span>
              <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 font-medium text-indigo-300">
                {(r.similarity_score * 100).toFixed(1)}% match
              </span>
            </div>
            <p className="text-sm leading-relaxed text-gray-300">{r.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
