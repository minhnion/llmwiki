import asyncio
import sqlite3

from backend.app.domain.agent import AnswerCitation, QueryAskCommand
from backend.app.repositories.operations import SQLiteOperationRepository
from backend.app.repositories.queries import SQLiteQueryRepository
from backend.app.services.query_agent import QueryAgentService, _ground_citations
from backend.app.services.source_ingest import SourceIngestService
from backend.app.services.wiki_log import WikiLogWriter
from backend.tests.fake_llm import FakeWikiAgentLLM
from backend.tests.helpers import build_test_context, register_text_source


def test_query_agent_answers_with_grounded_page_source_citation(tmp_path) -> None:
    database, wiki_dir, source_repository, store = build_test_context(tmp_path)
    source = register_text_source(tmp_path, database, wiki_dir)
    llm = FakeWikiAgentLLM()
    ingest = SourceIngestService(
        source_repository=source_repository,
        operation_repository=SQLiteOperationRepository(database),
        wiki_store=store,
        llm_client=llm,
        wiki_log_writer=WikiLogWriter(wiki_dir),
        max_file_bytes=1_000_000,
        search_limit=12,
    )
    asyncio.run(ingest.ingest(source.id))
    query = QueryAgentService(
        source_repository=source_repository,
        query_repository=SQLiteQueryRepository(database),
        operation_repository=SQLiteOperationRepository(database),
        wiki_store=store,
        llm_client=llm,
        wiki_log_writer=WikiLogWriter(wiki_dir),
        search_limit=12,
        source_limit=3,
    )

    result = asyncio.run(
        query.ask(QueryAskCommand(question="What is a persistent wiki?", mode="deep"))
    )

    assert result.confidence == "high"
    assert result.citations
    assert result.pages_read
    with sqlite3.connect(database.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM query_runs").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM operations WHERE operation_type = 'query'"
            ).fetchone()[0]
            == 1
        )


def test_query_grounding_rejects_unknown_locator(tmp_path) -> None:
    database, wiki_dir, source_repository, store = build_test_context(tmp_path)
    source = register_text_source(tmp_path, database, wiki_dir)
    llm = FakeWikiAgentLLM()
    ingest = SourceIngestService(
        source_repository=source_repository,
        operation_repository=SQLiteOperationRepository(database),
        wiki_store=store,
        llm_client=llm,
        wiki_log_writer=WikiLogWriter(wiki_dir),
        max_file_bytes=1_000_000,
        search_limit=12,
    )
    asyncio.run(ingest.ingest(source.id))
    pages = store.scan_pages()

    citations = _ground_citations(
        [
            AnswerCitation(
                page_id=pages[0].id,
                source_id=source.id,
                locator="invented locator",
                quote_or_summary="Invented support.",
            )
        ],
        pages,
        [],
    )

    assert citations == []
