from dataclasses import dataclass

from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import ingest_job_id
from backend.app.domain.extraction import IngestExtractionResult
from backend.app.domain.models import SourceRef, WikiPage
from backend.app.repositories.extractions import SQLiteExtractionRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.llm_client import LLMClient
from backend.app.services.source_page_writer import SourcePageWriter
from backend.app.services.wiki_log import WikiLogWriter


@dataclass(frozen=True)
class SourceIngestResult:
    source: SourceRef
    extraction: IngestExtractionResult
    page: WikiPage


class SourceIngestService:
    def __init__(
        self,
        source_repository: SQLiteSourceRepository,
        extraction_repository: SQLiteExtractionRepository,
        job_repository: SQLiteIngestJobRepository,
        llm_client: LLMClient,
        source_page_writer: SourcePageWriter,
        wiki_log_writer: WikiLogWriter,
        max_file_bytes: int,
    ) -> None:
        self.source_repository = source_repository
        self.extraction_repository = extraction_repository
        self.job_repository = job_repository
        self.llm_client = llm_client
        self.source_page_writer = source_page_writer
        self.wiki_log_writer = wiki_log_writer
        self.max_file_bytes = max_file_bytes

    async def ingest(self, source_id: str) -> SourceIngestResult:
        source = self.source_repository.get(source_id)
        if source is None:
            raise ValueError(f"Source not found: {source_id}")
        if source.size_bytes is not None and source.size_bytes > self.max_file_bytes:
            raise ValueError(
                f"Source file is too large for direct multimodal ingest: "
                f"{source.size_bytes} bytes > {self.max_file_bytes} bytes"
            )

        job_id = ingest_job_id()
        started_at = utc_now_iso()
        self.job_repository.create_ingest_job(job_id, source.id, started_at)
        try:
            extraction = await self.llm_client.extract_source(source)
            page = self.source_page_writer.write(source, extraction)
            self.extraction_repository.save(source, extraction, page)
            finished_at = utc_now_iso()
            self.job_repository.mark_completed(job_id, finished_at)
            self.wiki_log_writer.append_source_ingested(
                finished_at,
                source.id,
                extraction.source_title or source.title,
                page.path,
            )
            updated_source = self.source_repository.get(source.id) or source
            return SourceIngestResult(source=updated_source, extraction=extraction, page=page)
        except Exception as exc:
            self.job_repository.mark_failed(job_id, utc_now_iso(), str(exc))
            raise
