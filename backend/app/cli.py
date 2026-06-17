import argparse
import asyncio
from pathlib import Path

from backend.app.application.container import get_container
from backend.app.db.migrations import MigrationRunner
from backend.app.repositories.extractions import SQLiteExtractionRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.llm_client import OpenAIResponsesClient
from backend.app.services.source_ingest import SourceIngestService
from backend.app.services.source_page_writer import SourcePageWriter
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-wiki")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int)
    serve_parser.add_argument("--reload", action="store_true")

    db_parser = subparsers.add_parser("db")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)
    db_subparsers.add_parser("migrate")

    sources_parser = subparsers.add_parser("sources")
    sources_subparsers = sources_parser.add_subparsers(dest="sources_command", required=True)
    register_parser = sources_subparsers.add_parser("register")
    register_parser.add_argument("path")
    register_parser.add_argument("--title")
    register_parser.add_argument("--type", dest="source_type")
    register_parser.add_argument("--tag", dest="tags", action="append", default=[])
    ingest_parser = sources_subparsers.add_parser("ingest")
    ingest_parser.add_argument("source_id")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    container = get_container()

    if args.command == "serve":
        import uvicorn

        MigrationRunner(container.database).run()
        uvicorn.run(
            "backend.app.main:app",
            host=args.host,
            port=args.port or container.settings.port,
            reload=args.reload,
        )
        return

    if args.command == "db" and args.db_command == "migrate":
        applied = MigrationRunner(container.database).run()
        if not applied:
            print("Database already up to date.")
            return
        for migration in applied:
            print(f"Applied migration {migration.version}: {migration.name}")
        return

    if args.command == "sources" and args.sources_command == "register":
        MigrationRunner(container.database).run()
        service = SourceRegistryService(
            source_repository=SQLiteSourceRepository(container.database),
            job_repository=SQLiteIngestJobRepository(container.database),
            wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
        )
        source = service.register(
            RegisterSourceCommand(
                path=Path(args.path),
                title=args.title,
                source_type=args.source_type,
                tags=tuple(args.tags),
            )
        )
        print(f"Registered {source.id}: {source.title}")
        print(f"sha256: {source.sha256}")
        print(f"path: {source.path}")
        return

    if args.command == "sources" and args.sources_command == "ingest":
        MigrationRunner(container.database).run()
        if not container.settings.openai_api_key:
            raise SystemExit("OPENAI_API_KEY is required for ingest.")
        service = SourceIngestService(
            source_repository=SQLiteSourceRepository(container.database),
            extraction_repository=SQLiteExtractionRepository(container.database),
            job_repository=SQLiteIngestJobRepository(container.database),
            llm_client=OpenAIResponsesClient(
                api_key=container.settings.openai_api_key,
                model=container.settings.openai_model,
                max_output_tokens=container.settings.max_output_tokens,
            ),
            source_page_writer=SourcePageWriter(container.settings.wiki_dir),
            wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
            max_file_bytes=container.settings.max_file_bytes,
        )
        result = asyncio.run(service.ingest(args.source_id))
        print(f"Ingested {result.source.id}: {result.source.title}")
        print(f"page: {result.page.path}")
        print(f"evidence_items: {len(result.extraction.evidence_items)}")
        print(f"claims: {len(result.extraction.claims)}")
        print(f"entities: {len(result.extraction.entities)}")
        print(f"review_items: {len(result.extraction.review_items)}")
        return

    parser.error("Unsupported command")


if __name__ == "__main__":
    main()
