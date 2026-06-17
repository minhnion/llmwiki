from pydantic import BaseModel, ConfigDict, Field


class QueryAskCommand(BaseModel):
    question: str = Field(min_length=1)
    mode: str = Field(default="deep", description="fast, deep, or audit.")
    source_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    max_candidates: int = Field(default=24, ge=1, le=80)
    max_evidence: int = Field(default=8, ge=1, le=24)

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


class EvidenceAssessment(BaseModel):
    evidence_id: str
    relevance: str = Field(description="direct, indirect, background, conflicting, or irrelevant.")
    support_type: str = Field(description="supports, contradicts, qualifies, or irrelevant.")
    reason: str
    confidence: float = Field(ge=0, le=1)

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
