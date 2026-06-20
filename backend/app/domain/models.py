from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class SourceRef(BaseModel):
    id: str
    title: str
    path: Path
    source_type: str
    sha256: str
    mime_type: str | None = None
    size_bytes: int | None = None
    tags: list[str] = Field(default_factory=list)
    status: str = "registered"
    created_at: str | None = None
    updated_at: str | None = None
    ingested_at: str | None = None

    model_config = ConfigDict(extra="forbid")


class SourceVersion(BaseModel):
    id: str
    source_id: str
    sha256: str
    path: Path
    created_at: str

    model_config = ConfigDict(extra="forbid")


class EvidenceRef(BaseModel):
    id: str
    source_id: str
    locator: str
    quote_or_summary: str
    modality: str = "text"
    confidence: float = Field(default=1.0, ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class WikiPage(BaseModel):
    id: str
    path: Path
    title: str
    page_type: str
    summary: str
    body: str
    status: str = "active"
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    related_page_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str

    model_config = ConfigDict(extra="forbid")


class WikiPageSummary(BaseModel):
    id: str
    path: str
    title: str
    page_type: str
    summary: str
    status: str
    confidence: float
    source_ids: list[str]
    updated_at: str

    model_config = ConfigDict(extra="forbid")


class ReviewItem(BaseModel):
    id: str
    review_type: str
    title: str
    body: str
    severity: str
    status: str = "open"
    source_id: str | None = None
    page_id: str | None = None
    created_at: str

    model_config = ConfigDict(extra="forbid")
