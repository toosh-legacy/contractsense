import type {
  AnswerResponse,
  KeyTermsResponse,
  RiskReport,
  SearchResponse,
  UploadResponse,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * FastAPI returns errors as { detail: string } (or a list of validation
 * objects for 422s). Normalise both into a single readable message.
 */
async function toError(res: Response): Promise<Error> {
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail.map((d) => d.msg ?? JSON.stringify(d)).join("; ");
    }
  } catch {
    // Body wasn't JSON — keep the status-based message.
  }
  return new Error(message);
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new Error(
      `Cannot reach the API at ${API_URL}. Is the backend running?`,
    );
  }
  if (!res.ok) throw await toError(res);
  return res.json() as Promise<T>;
}

function withFile(file: File): RequestInit {
  const form = new FormData();
  form.append("file", file);
  return { method: "POST", body: form };
}

function withJson(payload: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

export const api = {
  /** Parse, chunk, embed and index a PDF so it can be searched. */
  upload: (file: File) => request<UploadResponse>("/upload", withFile(file)),

  /** Extract structured key terms (parties, dates, obligations). */
  extract: (file: File) => request<KeyTermsResponse>("/extract", withFile(file)),

  /** Score every clause LOW / MEDIUM / HIGH. */
  analyze: (file: File) => request<RiskReport>("/analyze", withFile(file)),

  /** Raw semantic search over an indexed contract. */
  search: (collection_name: string, query: string, n_results = 5) =>
    request<SearchResponse>(
      "/search",
      withJson({ collection_name, query, n_results }),
    ),

  /** Retrieval-augmented answer to a natural language question. */
  ask: (collection_name: string, question: string) =>
    request<AnswerResponse>("/ask", withJson({ collection_name, question })),

  health: () => request<{ status: string; version: string }>("/health", { method: "GET" }),
};
