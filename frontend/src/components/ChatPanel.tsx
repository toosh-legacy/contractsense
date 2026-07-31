"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { MarketSource } from "@/lib/types";
import { Button, ErrorBanner, Spinner } from "./ui";

interface Turn {
  question: string;
  answer: string;
  sources: string[];
  webSources: MarketSource[];
}

const SUGGESTIONS = [
  "Where can I push back on price?",
  "What renews or escalates automatically?",
  "How do these payment terms compare to the market?",
  "What are the three biggest risks to me here?",
];

export function ChatPanel({ collection }: { collection: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setError(null);
    setBusy(true);
    setQuestion("");
    try {
      const res = await api.advise(collection, q);
      setTurns((prev) => [
        ...prev,
        {
          question: q,
          answer: res.answer,
          sources: res.sources,
          webSources: res.web_sources,
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not answer that.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[62vh] flex-col">
      <div className="flex-1 space-y-5 overflow-y-auto pr-1">
        {turns.length === 0 && !busy && (
          <div className="pt-6">
            <p className="text-sm text-gray-400">
              Ask anything about this contract. Answers are grounded in the
              retrieved clauses, its assessment, and industry benchmarks — and
              the model will check the web when the question is about the
              current market.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => void ask(s)}
                  className="rounded-full border border-white/15 px-3 py-1.5 text-xs text-gray-300 transition hover:border-indigo-400/50 hover:bg-indigo-500/10"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i} className="animate-rise space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-indigo-500 px-4 py-2.5 text-sm text-white">
                {turn.question}
              </p>
            </div>
            <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-white/10 bg-white/[0.04] px-4 py-3">
              <p className="text-sm leading-relaxed whitespace-pre-wrap text-gray-200">
                {turn.answer}
              </p>
              {turn.sources.length > 0 && (
                <details className="mt-3 border-t border-white/10 pt-2">
                  <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-300">
                    {turn.sources.length} source
                    {turn.sources.length === 1 ? "" : "s"}
                  </summary>
                  <ul className="mt-2 space-y-2">
                    {turn.sources.map((s, j) => (
                      <li
                        key={j}
                        className="rounded-md bg-black/30 px-3 py-2 text-xs leading-relaxed text-gray-400"
                      >
                        {s}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {turn.webSources.length > 0 && (
                <details className="mt-2 border-t border-white/10 pt-2">
                  <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-300">
                    {turn.webSources.length} web source
                    {turn.webSources.length === 1 ? "" : "s"}
                  </summary>
                  <ul className="mt-2 space-y-1.5">
                    {turn.webSources.map((s) => (
                      <li key={s.url}>
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noreferrer"
                          className="block truncate text-xs text-indigo-300 hover:text-indigo-200 hover:underline"
                        >
                          {s.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Spinner /> Reading the contract…
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="pt-3">
          <ErrorBanner message={error} />
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
        className="mt-4 flex gap-2 border-t border-white/10 pt-4"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask for advice on this contract…"
          className="flex-1 rounded-lg border border-white/15 bg-black/30 px-4 py-2.5 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-indigo-400"
        />
        <Button type="submit" disabled={busy || !question.trim()}>
          Ask
        </Button>
      </form>
    </div>
  );
}
