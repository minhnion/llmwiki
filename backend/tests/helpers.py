from pathlib import Path

from backend.app.db.connection import SQLiteDatabase
from backend.app.db.migrations import MigrationRunner
from backend.app.repositories.operations import SQLiteOperationRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.repositories.wiki import SQLiteWikiRepository
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter
from backend.app.services.wiki_store import WikiStore


def build_test_context(tmp_path: Path):
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    MigrationRunner(database).run()
    wiki_dir = tmp_path / "wiki"
    source_repository = SQLiteSourceRepository(database)
    store = WikiStore(
        wiki_dir=wiki_dir,
        repository=SQLiteWikiRepository(database),
        source_repository=source_repository,
    )
    store.initialize()
    store.rebuild()
    return database, wiki_dir, source_repository, store


def register_text_source(
    tmp_path: Path,
    database: SQLiteDatabase,
    wiki_dir: Path,
    text: str = "A persistent wiki accumulates knowledge.",
):
    path = tmp_path / "source.md"
    path.write_text(text, encoding="utf-8")
    service = SourceRegistryService(
        source_repository=SQLiteSourceRepository(database),
        operation_repository=SQLiteOperationRepository(database),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    )
    return service.register(
        RegisterSourceCommand(path=path, title="Wiki Source", source_type="markdown")
    )
