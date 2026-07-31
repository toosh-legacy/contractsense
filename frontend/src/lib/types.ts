// Mirrors the Pydantic response models in backend/app/api/routes.py.

export type RiskLevel = "HIGH" | "MEDIUM" | "LOW";

export interface UploadResponse {
  filename: string;
  collection_name: string;
  total_pages: number;
  total_words: number;
  total_chunks: number;
  message: string;
}

export interface ChunkResult {
  text: string;
  page_num: number;
  chunk_index: number;
  similarity_score: number;
}

export interface SearchResponse {
  query: string;
  collection_name: string;
  results: ChunkResult[];
}

export interface KeyTermsResponse {
  filename: string;
  contract_type: string;
  parties: string[];
  effective_date: string | null;
  expiry_date: string | null;
  governing_law: string | null;
  key_obligations: string[];
}

export interface ClauseAnalysis {
  chunk_id: string;
  page_num: number;
  chunk_index: number;
  text_preview: string;
  clause_type: string;
  risk_level: RiskLevel;
  reason: string;
  recommendation: string;
}

export interface RiskReport {
  collection_name: string;
  overall_risk: RiskLevel;
  risk_counts: Record<RiskLevel, number>;
  total_clauses_analyzed: number;
  high_risk_clauses: ClauseAnalysis[];
  all_clauses: ClauseAnalysis[];
}

export interface AnswerResponse {
  question: string;
  answer: string;
  sources: string[];
}
