from abc import ABC, abstractmethod

from backend.app.domain.models import EvidenceItem, SourceRef, WikiPage


class SourceRepository(ABC):
    @abstractmethod
    def add(self, source: SourceRef) -> None:
        raise NotImplementedError


class EvidenceRepository(ABC):
    @abstractmethod
    def add(self, evidence: EvidenceItem) -> None:
        raise NotImplementedError


class WikiRepository(ABC):
    @abstractmethod
    def write_page(self, page: WikiPage) -> None:
        raise NotImplementedError


class IngestPipeline(ABC):
    @abstractmethod
    async def ingest(self, source: SourceRef) -> None:
        raise NotImplementedError
