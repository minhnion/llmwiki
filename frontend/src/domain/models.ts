export type SourceStatus = "registered" | "ingested" | string;

export interface SourceRef {
  id: string;
  title: string;
  path: string;
  source_type: string;
  sha256: string;
  mime_type: string | null;
  size_bytes: number | null;
  tags: string[];
  status: SourceStatus;
  created_at: string | null;
  updated_at: string | null;
}

export interface SourceIngestResult {
  source: SourceRef;
  page_path: string;
  evidence_count: number;
  claim_count: number;
  entity_count: number;
  review_item_count: number;
  compiler_run_id: string;
  pass_count: number;
  artifact_count: number;
  coverage_status: string;
  graph_run_id: string;
  relation_count: number;
  contradiction_count: number;
}

export interface Citation {
  evidence_id: string;
  source_id: string;
  source_title: string;
  locator: string;
  quote_or_summary: string;
  claim_ids: string[];
}

export interface EvidenceCandidate {
  evidence_id: string;
  source_id: string;
  source_title: string;
  source_path: string;
  wiki_page_path: string;
  locator: string;
  modality: string;
  text: string;
  summary: string;
  confidence: number;
  claim_ids: string[];
  claims: string[];
  entities: string[];
  retrieval_score: number;
  retrieval_channels: string[];
}

export interface QueryPlan {
  rewritten_question: string;
  intent: string;
  answer_language: string;
  retrieval_strategy: string;
  keywords: string[];
  entity_hints: string[];
  subquestions: string[];
  must_have_evidence: string[];
  source_filters: string[];
  time_filters: string[];
}

export interface QueryResult {
  query_id: string;
  question: string;
  mode: string;
  answer: string;
  confidence: string;
  citations: Citation[];
  used_claim_ids: string[];
  matched_entities: string[];
  contradictions: string[];
  open_questions: string[];
  follow_up_questions: string[];
  selected_evidence: EvidenceCandidate[];
  candidate_count: number;
  created_at: string;
  plan: QueryPlan;
}

export interface GraphBuildResult {
  graph_run_id: string;
  source_ids: string[];
  claim_count: number;
  relation_count: number;
  contradiction_count: number;
  merge_candidate_count: number;
  entity_page_count: number;
  status: string;
  started_at: string;
  finished_at: string;
}

export interface GraphNode {
  id: string;
  label: string;
  node_type: string;
  confidence: number | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  confidence: number;
  claim_id: string;
  evidence_id: string;
}

export interface GraphVisualization {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphEntity {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  aliases: string[];
  description: string;
  confidence: number;
}

export interface RelationEdge {
  id: string;
  subject_entity_id: string | null;
  subject_name: string;
  predicate: string;
  object_entity_id: string | null;
  object_value: string;
  object_type: string;
  claim_id: string;
  evidence_id: string;
  source_id: string;
  confidence: number;
  status: string;
  qualifiers: string[];
  created_at: string;
  updated_at: string;
}

export interface EntityMergeCandidate {
  id: string;
  entity_a_id: string | null;
  entity_b_id: string | null;
  entity_a_name: string;
  entity_b_name: string;
  reason: string;
  confidence: number;
  status: string;
  created_at: string;
}

export interface GraphEntityDetail {
  entity: GraphEntity;
  outgoing_relations: RelationEdge[];
  incoming_relations: RelationEdge[];
  merge_candidates: EntityMergeCandidate[];
  page_path: string | null;
}

export interface Contradiction {
  id: string;
  claim_a_id: string;
  claim_b_id: string;
  relationship: string;
  reason: string;
  confidence: number;
  status: string;
  evidence_ids: string[];
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: QueryResult;
  createdAt: string;
}
