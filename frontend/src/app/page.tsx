"use client";

import { useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { NegotiatePanel } from "@/components/NegotiatePanel";
import { RiskPanel } from "@/components/RiskPanel";
import { ScorePanel } from "@/components/ScorePanel";
import { SearchPanel } from "@/components/SearchPanel";
import { TermsPanel } from "@/components/TermsPanel";
import { UploadPanel } from "@/components/UploadPanel";
import { Button, Card } from "@/components/ui";
import type { UploadResponse } from "@/lib/types";

const TABS = [
  "Score",
  "Negotiate",
  "Ask",
  "Risk",
  "Key terms",
  "Search",
] as const;
type Tab = (typeof TABS)[number];

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [doc, setDoc] = useState<UploadResponse | null>(null);
  const [tab, setTab] = useState<Tab>("Score");

  function reset() {
    setFile(null);
    setDoc(null);
    setTab("Score");
  }

  return (
    <main className="mx-auto max-w-5xl px-5 py-10">
      <header className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-50">
            Contract<span className="text-indigo-400">Sense</span>
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Upload a contract. Score its risk, find where you can negotiate,
            and ask for advice.
          </p>
        </div>
        {doc && (
          <Button variant="ghost" onClick={reset}>
            New contract
          </Button>
        )}
      </header>

      {!doc || !file ? (
        <UploadPanel
          onUploaded={(f, result) => {
            setFile(f);
            setDoc(result);
          }}
        />
      ) : (
        <div className="animate-rise space-y-5">
          <Card className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-gray-100">
                {doc.filename}
              </p>
              <p className="mt-0.5 font-mono text-xs text-gray-600">
                {doc.collection_name}
              </p>
            </div>
            <dl className="flex gap-6 text-sm">
              <Meta label="Pages" value={doc.total_pages} />
              <Meta label="Words" value={doc.total_words.toLocaleString()} />
              <Meta label="Chunks" value={doc.total_chunks} />
            </dl>
          </Card>

          {/* Six tabs no longer fit in a row on a phone, so they wrap */}
          <nav className="flex flex-wrap gap-1 rounded-lg border border-white/10 bg-white/[0.02] p-1">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex-1 rounded-md px-3 py-2 text-sm font-medium whitespace-nowrap transition ${
                  tab === t
                    ? "bg-indigo-500 text-white"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                {t}
              </button>
            ))}
          </nav>

          <Card>
            {tab === "Score" && <ScorePanel collection={doc.collection_name} />}
            {tab === "Negotiate" && (
              <NegotiatePanel collection={doc.collection_name} />
            )}
            {tab === "Ask" && <ChatPanel collection={doc.collection_name} />}
            {tab === "Risk" && <RiskPanel file={file} />}
            {tab === "Key terms" && <TermsPanel file={file} />}
            {tab === "Search" && <SearchPanel collection={doc.collection_name} />}
          </Card>
        </div>
      )}
    </main>
  );
}

function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs tracking-wide text-gray-500 uppercase">{label}</dt>
      <dd className="mt-0.5 font-semibold text-gray-200">{value}</dd>
    </div>
  );
}
