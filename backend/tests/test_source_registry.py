import asyncio
import sqlite3

from backend.app.api.routes.sources import upload_source
from backend.app.application.container import AppContainer
from backend.app.core.config import Settings
from backend.app.db.connection import SQLiteDatabase
from backend.app.db.migrations import MigrationRunner
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter


class FakeUploadFile:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content = content
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.content):
            return b""
        if size < 0:
            size = len(self.content) - self.offset
        start = self.offset
        self.offset = min(len(self.content), self.offset + size)
        return self.content[start : self.offset]


def test_register_source_creates_records_and_log(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    MigrationRunner(database).run()
    source_path = tmp_path / "example.md"
    source_path.write_text("# Example\n\nHello wiki.\n", encoding="utf-8")
    wiki_dir = tmp_path / "wiki"
    service = SourceRegistryService(
        source_repository=SQLiteSourceRepository(database),
        job_repository=SQLiteIngestJobRepository(database),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    )

    source = service.register(
        RegisterSourceCommand(
            path=source_path,
            title="Example",
            source_type="markdown",
            tags=("test",),
        )
    )

    assert source.id.startswith("src_")
    assert source.title == "Example"
    assert source.source_type == "markdown"
    assert source.size_bytes == source_path.stat().st_size
    assert (wiki_dir / "log.md").exists()
    assert source.id in (wiki_dir / "log.md").read_text(encoding="utf-8")

    with sqlite3.connect(tmp_path / "app.sqlite") as connection:
        source_count = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        version_count = connection.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0]
        job_count = connection.execute("SELECT COUNT(*) FROM ingest_jobs").fetchone()[0]

    assert source_count == 1
    assert version_count == 1
    assert job_count == 1


def test_upload_source_endpoint_saves_file_and_registers_source(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    MigrationRunner(database).run()
    container = AppContainer(
        settings=Settings(
            database_path=tmp_path / "app.sqlite",
            raw_dir=tmp_path / "raw",
            wiki_dir=tmp_path / "wiki",
            openai_api_key="",
        ),
        database=database,
    )

    response = asyncio.run(
        upload_source(
            container=container,
            file=FakeUploadFile("Example Notes.md", b"# Example\n\nHello upload.\n"),
            title="Uploaded Notes",
            source_type="markdown",
            tags=["upload"],
        )
    )

    assert response.title == "Uploaded Notes"
    assert response.source_type == "markdown"
    assert response.status == "registered"
    assert (tmp_path / "raw" / "sources" / "example-notes.md").exists()

    with sqlite3.connect(tmp_path / "app.sqlite") as connection:
        source_count = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert source_count == 1


def test_upload_source_endpoint_recognizes_odt(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    MigrationRunner(database).run()
    container = AppContainer(
        settings=Settings(
            database_path=tmp_path / "app.sqlite",
            raw_dir=tmp_path / "raw",
            wiki_dir=tmp_path / "wiki",
            openai_api_key="",
        ),
        database=database,
    )

    response = asyncio.run(
        upload_source(
            container=container,
            file=FakeUploadFile("Quy dinh.odt", b"fake odt package"),
        )
    )

    assert response.source_type == "odt"
    assert response.mime_type == "application/vnd.oasis.opendocument.text"
    assert response.path.endswith(".odt")
