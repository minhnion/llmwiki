from pydantic import BaseModel, ConfigDict

from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import operation_id, review_id
from backend.app.core.source_integrity import verify_source
from backend.app.domain.contracts import WikiAgentLLM
from backend.app.domain.models import ReviewItem, SourceRef
from backend.app.repositories.operations import SQLiteOperationRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.wiki_log import WikiLogWriter
from backend.app.services.wiki_store import WikiStore


class SourceIngestResult(BaseModel):
    source: SourceRef
    operation_id: str
    skipped: bool
    changed_page_ids: list[str]
    changed_page_paths: list[str]
    review_count: int
    model_calls: int
    input_tokens: int
    output_tokens: int

    model_config = ConfigDict(extra="forbid")


class SourceIngestService:
    def __init__(
        self,
        source_repository: SQLiteSourceRepository,
        operation_repository: SQLiteOperationRepository,
        wiki_store: WikiStore,
        llm_client: WikiAgentLLM,
        wiki_log_writer: WikiLogWriter,
        max_file_bytes: int,
        search_limit: int,
    ) -> None:
        self.source_repository = source_repository
        self.operation_repository = operation_repository
        self.wiki_store = wiki_store
        self.llm_client = llm_client
        self.wiki_log_writer = wiki_log_writer
        self.max_file_bytes = max_file_bytes
        self.search_limit = search_limit

    async def ingest(self, source_id: str, force: bool = False) -> SourceIngestResult:
        source = self.source_repository.get(source_id)
        if source is None:
            raise ValueError(f"Source not found: {source_id}")
        verify_source(source)
        if source.size_bytes and source.size_bytes > self.max_file_bytes:
            raise ValueError(
                f"Source exceeds direct file-input limit: "
                f"{source.size_bytes} > {self.max_file_bytes}"
            )
        if source.status == "ingested" and not force:
            return SourceIngestResult(
                source=source,
                operation_id="",
                skipped=True,
                changed_page_ids=[],
                changed_page_paths=[],
                review_count=0,
                model_calls=0,
                input_tokens=0,
                output_tokens=0,
            )

        current_operation_id = operation_id()
        started_at = utc_now_iso()
        self.operation_repository.start(
            current_operation_id,
            "ingest",
            source.id,
            started_at,
            {"source_sha256": source.sha256},
        )
        self.source_repository.mark_status(source.id, "ingesting", started_at)
        try:
            self.wiki_store.rebuild()
            analysis, analysis_usage = await self.llm_client.analyze_source(
                source=source,
                purpose=self.wiki_store.read_special("purpose.md"),
                schema=self.wiki_store.read_special("schema.md"),
                catalog=self.wiki_store.catalog(),
            )
            self.operation_repository.record_llm_call(
                current_operation_id,
                "understand",
                analysis_usage,
            )
            relevant_pages = self.wiki_store.search(
                analysis.wiki_search_queries,
                self.search_limit,
            )
            relevant_pages = self.wiki_store.get_pages(
                list(
                    dict.fromkeys(
                        [
                            *analysis.relevant_page_ids,
                            *[page.id for page in relevant_pages],
                        ]
                    )
                )[: self.search_limit]
            )
            change_set, maintain_usage = await self.llm_client.propose_wiki_changes(
                source=source,
                purpose=self.wiki_store.read_special("purpose.md"),
                schema=self.wiki_store.read_special("schema.md"),
                analysis=analysis,
                relevant_pages=relevant_pages,
            )
            self.operation_repository.record_llm_call(
                current_operation_id,
                "maintain",
                maintain_usage,
            )
            if not any(
                evidence.source_id == source.id
                for change in change_set.changes
                if change.action != "delete"
                for evidence in change.evidence
            ):
                raise ValueError(
                    "Wiki change set contains no evidence from the ingested source."
                )
            changed_pages = self.wiki_store.apply_change_set(change_set)
            reviews = [
                ReviewItem(
                    id=review_id(),
                    review_type=item.review_type,
                    title=item.title,
                    body=item.body,
                    severity=item.severity,
                    source_id=item.source_id,
                    page_id=item.page_id,
                    created_at=utc_now_iso(),
                )
                for item in change_set.reviews
            ]
            self.operation_repository.save_reviews(reviews)
            finished_at = utc_now_iso()
            updated_source = (
                self.source_repository.mark_status(source.id, "ingested", finished_at)
                or source
            )
            totals = {
                "model_calls": 2,
                "input_tokens": analysis_usage.input_tokens + maintain_usage.input_tokens,
                "output_tokens": analysis_usage.output_tokens + maintain_usage.output_tokens,
                "changed_page_ids": [page.id for page in changed_pages],
                "review_count": len(reviews),
            }
            self.operation_repository.complete(
                current_operation_id,
                finished_at,
                totals,
            )
            self.wiki_log_writer.append(
                finished_at,
                "ingest",
                source.title,
                {
                    "source_id": source.id,
                    "operation_id": current_operation_id,
                    "pages_changed": len(changed_pages),
                    "reviews": len(reviews),
                },
            )
            return SourceIngestResult(
                source=updated_source,
                operation_id=current_operation_id,
                skipped=False,
                changed_page_ids=[page.id for page in changed_pages],
                changed_page_paths=[
                    page.path.relative_to(self.wiki_store.wiki_dir).as_posix()
                    for page in changed_pages
                ],
                review_count=len(reviews),
                model_calls=2,
                input_tokens=totals["input_tokens"],
                output_tokens=totals["output_tokens"],
            )
        except Exception as exc:
            failed_at = utc_now_iso()
            self.operation_repository.fail(current_operation_id, failed_at, str(exc))
            self.source_repository.mark_status(source.id, "failed", failed_at)
            raise
