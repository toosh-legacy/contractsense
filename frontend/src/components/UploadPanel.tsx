"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import type { UploadResponse } from "@/lib/types";
import { Button, ErrorBanner, Spinner } from "./ui";

export function UploadPanel({
  onUploaded,
}: {
  onUploaded: (file: File, result: UploadResponse) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const result = await api.upload(file);
      onUploaded(file, result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void handle(e.dataTransfer.files[0]);
        }}
        className={`rounded-2xl border-2 border-dashed p-12 text-center transition ${
          dragging
            ? "border-indigo-400 bg-indigo-500/10"
            : "border-white/15 bg-white/[0.02]"
        }`}
      >
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl bg-indigo-500/15 text-2xl">
          📄
        </div>
        <p className="text-base font-medium text-gray-100">
          Drop a contract PDF here
        </p>
        <p className="mt-1 text-sm text-gray-500">
          It gets parsed, chunked, embedded and indexed for search.
        </p>

        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => void handle(e.target.files?.[0])}
        />

        <div className="mt-6">
          <Button onClick={() => inputRef.current?.click()} disabled={busy}>
            {busy && <Spinner />}
            {busy ? "Processing…" : "Choose a PDF"}
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
    </div>
  );
}
