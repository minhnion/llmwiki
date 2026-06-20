from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceAnalysis(BaseModel):
    summary: str
    relevant_page_ids: list[str]
    wiki_search_queries: list[str]
    possible_conflicts: list[str]
    uncertainties: list[str]

    model_config = ConfigDict(extra="forbid")


class EvidenceDraft(BaseModel):
    source_id: str
    locator: str
    quote_or_summary: str
    modality: str
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class PageChange(BaseModel):
    action: Literal["create", "update", "delete"]
    page_id: str | None
    path: str
    title: str
    page_type: str
    summary: str
    body: str
    status: Literal["active", "needs_review", "archived"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceDraft]
    related_page_ids: list[str]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_action(self) -> "PageChange":
        if self.action in {"update", "delete"} and not self.page_id:
            raise ValueError(f"{self.action} requires page_id.")
        if self.action != "delete" and not self.body.strip():
            raise ValueError("Created or updated pages require a Markdown body.")
        return self


class ReviewDraft(BaseModel):
    review_type: str
    title: str
    body: str
    severity: str
    source_id: str | None
    page_id: str | None

    model_config = ConfigDict(extra="forbid")


class WikiChangeSet(BaseModel):
    changes: list[PageChange]
    reviews: list[ReviewDraft]
    overview_body: str | None
    notes: list[str]

    model_config = ConfigDict(extra="forbid")


class QueryPlan(BaseModel):
    search_queries: list[str]
    page_ids: list[str]
    source_ids_to_inspect: list[str]
    answer_language: str
    notes: list[str]

    model_config = ConfigDict(extra="forbid")


class AnswerCitation(BaseModel):
    page_id: str
    source_id: str | None
    locator: str
    quote_or_summary: str

    model_config = ConfigDict(extra="forbid")


class AgentAnswer(BaseModel):
    answer: str
    confidence: Literal["high", "medium", "low", "insufficient"]
    citations: list[AnswerCitation]
    open_questions: list[str]
    reusable_summary: str | None

    model_config = ConfigDict(extra="forbid")


class QueryAskCommand(BaseModel):
    question: str = Field(min_length=1)
    mode: Literal["fast", "deep", "audit"] = "deep"
    source_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class QueryResult(BaseModel):
    query_id: str
    question: str
    mode: str
    answer: str
    confidence: str
    citations: list[AnswerCitation]
    open_questions: list[str]
    pages_read: list[str]
    sources_inspected: list[str]
    created_at: str

    model_config = ConfigDict(extra="forbid")
