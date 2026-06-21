export interface SourceRef {
  id: string;
  title: string;
  path: string;
  source_type: string;
  sha256: string;
  mime_type: string | null;
  size_bytes: number | null;
  tags: string[];
  status: string;
  created_at: string | null;
  updated_at: string | null;
  ingested_at: string | null;
}

export interface SourceIngestResult {
  source: SourceRef;
  operation_id: string;
  skipped: boolean;
  changed_page_ids: string[];
  changed_page_paths: string[];
  review_count: number;
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
}

export interface AnswerCitation {
  page_id: string;
  source_id: string | null;
  locator: string;
  quote_or_summary: string;
}

export interface QueryResult {
  query_id: string;
  question: string;
  mode: string;
  answer: string;
  confidence: string;
  citations: AnswerCitation[];
  open_questions: string[];
  pages_read: string[];
  sources_inspected: string[];
  created_at: string;
}

export interface EvidenceRef {
  id: string;
  source_id: string;
  locator: string;
  quote_or_summary: string;
  modality: string;
  confidence: number;
}

export interface WikiPageSummary {
  id: string;
  path: string;
  title: string;
  page_type: string;
  summary: string;
  status: string;
  confidence: number;
  source_ids: string[];
  updated_at: string;
}

export interface WikiPage {
  id: string;
  path: string;
  title: string;
  page_type: string;
  summary: string;
  body: string;
  status: string;
  confidence: number;
  evidence_refs: EvidenceRef[];
  related_page_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: QueryResult;
  createdAt: string;
}
