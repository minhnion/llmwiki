import asyncio
import sqlite3

from backend.app.repositories.operations import SQLiteOperationRepository
from backend.app.services.source_ingest import SourceIngestService
from backend.app.services.wiki_log import WikiLogWriter
from backend.tests.fake_llm import FakeWikiAgentLLM
from backend.tests.helpers import build_test_context, register_text_source


def test_agentic_ingest_uses_two_model_calls_and_updates_wiki(tmp_path) -> None:
    database, wiki_dir, source_repository, store = build_test_context(tmp_path)
    source = register_text_source(tmp_path, database, wiki_dir)
    service = SourceIngestService(
        source_repository=source_repository,
        operation_repository=SQLiteOperationRepository(database),
        wiki_store=store,
        llm_client=FakeWikiAgentLLM(),
        wiki_log_writer=WikiLogWriter(wiki_dir),
        max_file_bytes=1_000_000,
        search_limit=12,
    )

    result = asyncio.run(service.ingest(source.id))

    assert result.model_calls == 2
    assert len(result.changed_page_ids) == 2
    assert result.review_count == 1
    assert source_repository.get(source.id).status == "ingested"
    assert (wiki_dir / "sources" / "wiki-source.md").exists()
    assert (wiki_dir / "pages" / "persistent-wiki.md").exists()
    with sqlite3.connect(database.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM review_items").fetchone()[0] == 1
