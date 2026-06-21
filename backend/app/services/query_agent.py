from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import operation_id, query_id
from backend.app.core.source_integrity import verify_source
from backend.app.domain.agent import AnswerCitation, QueryAskCommand, QueryResult
from backend.app.domain.contracts import WikiAgentLLM
from backend.app.repositories.operations import SQLiteOperationRepository
from backend.app.repositories.queries import SQLiteQueryRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.wiki_log import WikiLogWriter
from backend.app.services.wiki_store import WikiStore


class QueryAgentService:
    def __init__(
        self,
        source_repository: SQLiteSourceRepository,
        query_repository: SQLiteQueryRepository,
        operation_repository: SQLiteOperationRepository,
        wiki_store: WikiStore,
        llm_client: WikiAgentLLM,
        wiki_log_writer: WikiLogWriter,
        search_limit: int,
        source_limit: int,
    ) -> None:
        self.source_repository = source_repository
        self.query_repository = query_repository
        self.operation_repository = operation_repository
        self.wiki_store = wiki_store
        self.llm_client = llm_client
        self.wiki_log_writer = wiki_log_writer
        self.search_limit = search_limit
        self.source_limit = source_limit

    async def ask(self, command: QueryAskCommand) -> QueryResult:
        question = command.question.strip()
        if not question:
            raise ValueError("Question must not be blank.")
        current_operation_id = operation_id()
        created_at = utc_now_iso()
        self.operation_repository.start(
            current_operation_id,
            "query",
            None,
            created_at,
            {"mode": command.mode, "question": question},
        )
        try:
            self.wiki_store.rebuild()
            catalog = self.wiki_store.catalog(command.source_ids)
            known_source_ids = {
                source.id for source in self.source_repository.list()
            }
            unknown_source_ids = set(command.source_ids) - known_source_ids
            if unknown_source_ids:
                raise ValueError(
                    f"Unknown query source IDs: {sorted(unknown_source_ids)}"
                )
            allowed_sources = (
                self.source_repository.get_many(command.source_ids)
                if command.source_ids
                else self.source_repository.list()
            )
            plan, plan_usage = await self.llm_client.plan_query(
                question=question,
                mode=command.mode,
                purpose=self.wiki_store.read_special("purpose.md"),
                overview=self.wiki_store.read_special("overview.md"),
                index=self.wiki_store.read_special("index.md"),
                catalog=catalog,
                sources=allowed_sources,
            )
            self.operation_repository.record_llm_call(
                current_operation_id,
                "query_plan",
                plan_usage,
            )
            catalog_ids = {item.id for item in catalog}
            requested_page_ids = [
                page_id for page_id in plan.page_ids if page_id in catalog_ids
            ]
            searched_pages = self.wiki_store.search(
                plan.search_queries,
                self.search_limit,
                command.source_ids,
            )
            pages = self.wiki_store.get_pages(
                list(
                    dict.fromkeys(
                        [
                            *requested_page_ids,
                            *[page.id for page in searched_pages],
                        ]
                    )
                )[: self.search_limit]
            )

            allowed_source_ids = {source.id for source in allowed_sources}
            raw_source_budget = 0 if command.mode == "fast" else self.source_limit
            source_ids = [
                source_id
                for source_id in plan.source_ids_to_inspect
                if source_id in allowed_source_ids
            ][:raw_source_budget]
            sources = self.source_repository.get_many(source_ids)
            for source in sources:
                verify_source(source)
            answer, answer_usage = await self.llm_client.answer_query(
                question=question,
                mode=command.mode,
                plan=plan,
                pages=pages,
                sources=sources,
            )
            self.operation_repository.record_llm_call(
                current_operation_id,
                "answer",
                answer_usage,
            )
            citations = _ground_citations(answer.citations, pages, source_ids)
            result = QueryResult(
                query_id=query_id(),
                question=question,
                mode=command.mode,
                answer=answer.answer,
                confidence=answer.confidence if citations else _without_citation(answer.confidence),
                citations=citations,
                open_questions=answer.open_questions,
                pages_read=[page.id for page in pages],
                sources_inspected=[source.id for source in sources],
                created_at=created_at,
            )
            self.query_repository.save(result)
            self.operation_repository.complete(
                current_operation_id,
                utc_now_iso(),
                {
                    "query_id": result.query_id,
                    "pages_read": result.pages_read,
                    "sources_inspected": result.sources_inspected,
                    "citation_count": len(result.citations),
                },
            )
            self.wiki_log_writer.append(
                created_at,
                "query",
                result.query_id,
                {
                    "question": question,
                    "confidence": result.confidence,
                    "citations": len(result.citations),
                },
            )
            return result
        except Exception as exc:
            self.operation_repository.fail(current_operation_id, utc_now_iso(), str(exc))
            raise


def _ground_citations(
    citations: list[AnswerCitation],
    pages,
    inspected_source_ids: list[str],
) -> list[AnswerCitation]:
    pages_by_id = {page.id: page for page in pages}
    evidence_by_page = {
        page.id: {
            (item.source_id, item.locator): item for item in page.evidence_refs
        }
        for page in pages
    }
    inspected = set(inspected_source_ids)
    output: list[AnswerCitation] = []
    for citation in citations:
        if citation.page_id not in pages_by_id:
            continue
        if citation.source_id is None:
            output.append(citation)
            continue
        if citation.source_id in inspected:
            output.append(citation)
            continue
        evidence = evidence_by_page[citation.page_id].get(
            (citation.source_id, citation.locator)
        )
        if evidence is None:
            continue
        output.append(
            AnswerCitation(
                page_id=citation.page_id,
                source_id=citation.source_id,
                locator=evidence.locator,
                quote_or_summary=evidence.quote_or_summary,
            )
        )
    return output


def _without_citation(confidence: str) -> str:
    return "low" if confidence in {"high", "medium"} else confidence
