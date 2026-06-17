from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceRef:
    id: str
    title: str
    path: Path
    source_type: str
    sha256: str
    mime_type: str | None = None
    size_bytes: int | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    status: str = "registered"
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class SourceVersion:
    id: str
    source_id: str
    sha256: str
    path: Path
    created_at: str


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    source_id: str
    locator: str
    modality: str
    text: str | None = None
    summary: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    confidence: float | None = None


@dataclass(frozen=True)
class WikiPage:
    id: str
    title: str
    page_type: str
    path: Path
    body: str
    summary: str = ""
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    claim_ids: tuple[str, ...] = field(default_factory=tuple)
    sha256: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
