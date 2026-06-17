from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceRef:
    id: str
    title: str
    path: Path
    source_type: str
    sha256: str


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
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    claim_ids: tuple[str, ...] = field(default_factory=tuple)
