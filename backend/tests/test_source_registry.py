import sqlite3

from fastapi.testclient import TestClient

from backend.app.application.container import AppContainer, get_container
from backend.app.core.config import Settings
from backend.app.db.connection import SQLiteDatabase
from backend.app.db.migrations import MigrationRunner
from backend.app.main import create_app
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter


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
    app = create_app()
    app.dependency_overrides[get_container] = lambda: AppContainer(
        settings=Settings(
            database_path=tmp_path / "app.sqlite",
            raw_dir=tmp_path / "raw",
            wiki_dir=tmp_path / "wiki",
            openai_api_key="",
        ),
        database=database,
    )
    client = TestClient(app)

    response = client.post(
        "/api/sources/upload",
        files={"file": ("Example Notes.md", b"# Example\n\nHello upload.\n", "text/markdown")},
        data={"title": "Uploaded Notes", "source_type": "markdown", "tags": "upload"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Uploaded Notes"
    assert payload["source_type"] == "markdown"
    assert payload["status"] == "registered"
    assert (tmp_path / "raw" / "sources" / "example-notes.md").exists()

    with sqlite3.connect(tmp_path / "app.sqlite") as connection:
        source_count = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert source_count == 1


def test_upload_source_endpoint_recognizes_odt(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    MigrationRunner(database).run()
    app = create_app()
    app.dependency_overrides[get_container] = lambda: AppContainer(
        settings=Settings(
            database_path=tmp_path / "app.sqlite",
            raw_dir=tmp_path / "raw",
            wiki_dir=tmp_path / "wiki",
            openai_api_key="",
        ),
        database=database,
    )
    client = TestClient(app)

    response = client.post(
        "/api/sources/upload",
        files={
            "file": (
                "Quy dinh.odt",
                b"fake odt package",
                "application/vnd.oasis.opendocument.text",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_type"] == "odt"
    assert payload["mime_type"] == "application/vnd.oasis.opendocument.text"
    assert payload["path"].endswith(".odt")
