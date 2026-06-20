from pydantic import BaseModel, ConfigDict, Field


class QueryAskCommand(BaseModel):
    question: str = Field(min_length=1)
    mode: str = Field(default="deep", description="fast, deep, or audit.")
    source_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    max_candidates: int = Field(default=24, ge=1, le=80)
    max_evidence: int = Field(default=8, ge=1, le=24)

    model_config = ConfigDict(extra="forbid")


class QueryGraphPolicy(BaseModel):
    max_depth: int = Field(default=1, ge=0, le=3)
    max_nodes: int = Field(default=12, ge=0, le=80)
    relation_hints: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class QueryPlan(BaseModel):
    rewritten_question: str
    intent: str
    answer_language: str
    retrieval_strategy: str
    keywords: list[str]
    entity_hints: list[str]
    subquestions: list[str]
    must_have_evidence: list[str]
    source_filters: list[str]
    time_filters: list[str]
    semantic_probes: list[str] = Field(default_factory=list)
    desired_artifact_hints: list[str] = Field(default_factory=list)
    answer_requirements: list[str] = Field(default_factory=list)
    evidence_strictness: str = Field(default="medium")
    graph_policy: QueryGraphPolicy = Field(default_factory=QueryGraphPolicy)

    model_config = ConfigDict(extra="forbid")


class RetrievalSignal(BaseModel):
    channel: str
    rank: int = Field(ge=1)
    score: float
    detail: str

    model_config = ConfigDict(extra="forbid")


class EvidenceCandidate(BaseModel):
    evidence_id: str
    source_id: str
    source_title: str
    source_path: str
    wiki_page_path: str
    locator: str
    modality: str
    text: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    claim_ids: list[str]
    claims: list[str]
    entities: list[str]
    retrieval_score: float
    retrieval_channels: list[str]

    model_config = ConfigDict(extra="forbid")


class ArtifactStatementCandidate(BaseModel):
    statement_id: str
    statement_type: str
    text: str
    subject: str
    predicate: str
    object: str
    confidence: float = Field(ge=0, le=1)
    status: str
    evidence_ids: list[str]

    model_config = ConfigDict(extra="forbid")


class ArtifactCandidate(BaseModel):
    artifact_id: str
    source_id: str
    source_title: str
    source_path: str
    wiki_page_path: str
    artifact_type: str
    title: str
    summary: str
    content: str
    aliases: list[str]
    scope: list[str]
    confidence: float = Field(ge=0, le=1)
    status: str
    review_status: str
    statements: list[ArtifactStatementCandidate]
    evidence: list[EvidenceCandidate]
    retrieval_score: float
    retrieval_channels: list[str]
    retrieval_signals: list[RetrievalSignal]
    graph_depth: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class EvidenceAssessment(BaseModel):
    evidence_id: str
    relevance: str = Field(description="direct, indirect, background, conflicting, or irrelevant.")
    support_type: str = Field(description="supports, contradicts, qualifies, or irrelevant.")
    reason: str
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class KnowledgeMapEntryCandidate(BaseModel):
    entry_id: str
    parent_entry_id: str | None
    page_id: str | None
    artifact_id: str | None
    entry_type: str
    title: str
    summary: str
    source_ids: list[str]

    model_config = ConfigDict(extra="forbid")


class NavigationArtifactSelection(BaseModel):
    artifact_id: str
    reason: str
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class KnowledgeNavigationResult(BaseModel):
    selected_artifacts: list[NavigationArtifactSelection]
    relevant_map_entry_ids: list[str]
    missing_map_areas: list[str]
    reasoning_summary: str

    model_config = ConfigDict(extra="forbid")


class ArtifactAssessment(BaseModel):
    artifact_id: str
    relevance: str = Field(
        description="direct, supporting, qualifying, conflicting, background, or irrelevant."
    )
    support_type: str = Field(description="supports, contradicts, qualifies, or irrelevant.")
    selected_evidence_ids: list[str]
    reason: str
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class ArtifactRankingResult(BaseModel):
    selected_artifact_ids: list[str]
    rejected_artifact_ids: list[str]
    selected_evidence_ids: list[str]
    assessments: list[ArtifactAssessment]
    contradictions: list[str]
    missing_knowledge: list[str]
    reasoning_summary: str

    model_config = ConfigDict(extra="forbid")


class EvidenceRankingResult(BaseModel):
    selected_evidence_ids: list[str]
    rejected_evidence_ids: list[str]
    assessments: list[EvidenceAssessment]
    contradictions: list[str]
    missing_evidence: list[str]
    reasoning_summary: str

    model_config = ConfigDict(extra="forbid")


class Citation(BaseModel):
    evidence_id: str
    source_id: str
    source_title: str
    locator: str
    quote_or_summary: str
    claim_ids: list[str]

    model_config = ConfigDict(extra="forbid")


class QuerySynthesisResult(BaseModel):
    answer: str
    confidence: str = Field(description="high, medium, low, or insufficient.")
    citations: list[Citation]
    used_claim_ids: list[str]
    matched_entities: list[str]
    contradictions: list[str]
    open_questions: list[str]
    follow_up_questions: list[str]

    model_config = ConfigDict(extra="forbid")


class QueryResult(QuerySynthesisResult):
    query_id: str
    question: str
    mode: str
    plan: QueryPlan
    selected_evidence: list[EvidenceCandidate]
    candidate_count: int
    created_at: str


QUERY_PLAN_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rewritten_question": {"type": "string"},
        "intent": {"type": "string"},
        "answer_language": {"type": "string"},
        "retrieval_strategy": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "entity_hints": {"type": "array", "items": {"type": "string"}},
        "subquestions": {"type": "array", "items": {"type": "string"}},
        "must_have_evidence": {"type": "array", "items": {"type": "string"}},
        "source_filters": {"type": "array", "items": {"type": "string"}},
        "time_filters": {"type": "array", "items": {"type": "string"}},
        "semantic_probes": {"type": "array", "items": {"type": "string"}},
        "desired_artifact_hints": {"type": "array", "items": {"type": "string"}},
        "answer_requirements": {"type": "array", "items": {"type": "string"}},
        "evidence_strictness": {"type": "string"},
        "graph_policy": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "max_depth": {"type": "integer"},
                "max_nodes": {"type": "integer"},
                "relation_hints": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["max_depth", "max_nodes", "relation_hints"],
        },
    },
    "required": [
        "rewritten_question",
        "intent",
        "answer_language",
        "retrieval_strategy",
        "keywords",
        "entity_hints",
        "subquestions",
        "must_have_evidence",
        "source_filters",
        "time_filters",
        "semantic_probes",
        "desired_artifact_hints",
        "answer_requirements",
        "evidence_strictness",
        "graph_policy",
    ],
}


KNOWLEDGE_NAVIGATION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "selected_artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "artifact_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["artifact_id", "reason", "confidence"],
            },
        },
        "relevant_map_entry_ids": {"type": "array", "items": {"type": "string"}},
        "missing_map_areas": {"type": "array", "items": {"type": "string"}},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "selected_artifacts",
        "relevant_map_entry_ids",
        "missing_map_areas",
        "reasoning_summary",
    ],
}


ARTIFACT_RANKING_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "selected_artifact_ids": {"type": "array", "items": {"type": "string"}},
        "rejected_artifact_ids": {"type": "array", "items": {"type": "string"}},
        "selected_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "artifact_id": {"type": "string"},
                    "relevance": {"type": "string"},
                    "support_type": {"type": "string"},
                    "selected_evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "artifact_id",
                    "relevance",
                    "support_type",
                    "selected_evidence_ids",
                    "reason",
                    "confidence",
                ],
            },
        },
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "missing_knowledge": {"type": "array", "items": {"type": "string"}},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "selected_artifact_ids",
        "rejected_artifact_ids",
        "selected_evidence_ids",
        "assessments",
        "contradictions",
        "missing_knowledge",
        "reasoning_summary",
    ],
}


EVIDENCE_RANKING_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "selected_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "rejected_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "evidence_id": {"type": "string"},
                    "relevance": {"type": "string"},
                    "support_type": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "evidence_id",
                    "relevance",
                    "support_type",
                    "reason",
                    "confidence",
                ],
            },
        },
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "missing_evidence": {"type": "array", "items": {"type": "string"}},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "selected_evidence_ids",
        "rejected_evidence_ids",
        "assessments",
        "contradictions",
        "missing_evidence",
        "reasoning_summary",
    ],
}


QUERY_SYNTHESIS_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "evidence_id": {"type": "string"},
                    "source_id": {"type": "string"},
                    "source_title": {"type": "string"},
                    "locator": {"type": "string"},
                    "quote_or_summary": {"type": "string"},
                    "claim_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "evidence_id",
                    "source_id",
                    "source_title",
                    "locator",
                    "quote_or_summary",
                    "claim_ids",
                ],
            },
        },
        "used_claim_ids": {"type": "array", "items": {"type": "string"}},
        "matched_entities": {"type": "array", "items": {"type": "string"}},
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "answer",
        "confidence",
        "citations",
        "used_claim_ids",
        "matched_entities",
        "contradictions",
        "open_questions",
        "follow_up_questions",
    ],
}
