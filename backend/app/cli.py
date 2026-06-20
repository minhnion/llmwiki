import argparse
import asyncio
import json
from pathlib import Path

from backend.app.api.routes.sources import build_source_registry
from backend.app.application.container import get_container
from backend.app.application.factory import (
    build_query_agent,
    build_source_ingest,
    build_wiki_store,
)
from backend.app.db.migrations import MigrationRunner
from backend.app.domain.agent import QueryAskCommand
from backend.app.services.source_registry import RegisterSourceCommand


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-wiki")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int)
    serve.add_argument("--reload", action="store_true")

    db = subparsers.add_parser("db")
    db_subparsers = db.add_subparsers(dest="db_command", required=True)
    db_subparsers.add_parser("migrate")

    sources = subparsers.add_parser("sources")
    source_subparsers = sources.add_subparsers(dest="sources_command", required=True)
    register = source_subparsers.add_parser("register")
    register.add_argument("path")
    register.add_argument("--title")
    register.add_argument("--type", dest="source_type")
    register.add_argument("--tag", dest="tags", action="append", default=[])
    ingest = source_subparsers.add_parser("ingest")
    ingest.add_argument("source_id")
    ingest.add_argument("--force", action="store_true")

    query = subparsers.add_parser("query")
    query_subparsers = query.add_subparsers(dest="query_command", required=True)
    ask = query_subparsers.add_parser("ask")
    ask.add_argument("question", nargs="+")
    ask.add_argument("--mode", choices=["fast", "deep", "audit"], default="deep")
    ask.add_argument("--source-id", dest="source_ids", action="append", default=[])
    ask.add_argument("--json", action="store_true")

    wiki = subparsers.add_parser("wiki")
    wiki_subparsers = wiki.add_subparsers(dest="wiki_command", required=True)
    wiki_subparsers.add_parser("rebuild")
    wiki_subparsers.add_parser("list")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    container = get_container()

    if args.command == "serve":
        import uvicorn

        MigrationRunner(container.database).run()
        build_wiki_store(container).rebuild()
        uvicorn.run(
            "backend.app.main:app",
            host=args.host,
            port=args.port or container.settings.port,
            reload=args.reload,
        )
        return

    if args.command == "db":
        applied = MigrationRunner(container.database).run()
        for migration in applied:
            print(f"Applied migration {migration.version}: {migration.name}")
        if not applied:
            print("Database already up to date.")
        return

    MigrationRunner(container.database).run()
    build_wiki_store(container).initialize()

    if args.command == "sources" and args.sources_command == "register":
        source = build_source_registry(container).register(
            RegisterSourceCommand(
                path=Path(args.path),
                title=args.title,
                source_type=args.source_type,
                tags=tuple(args.tags),
            )
        )
        print(f"Registered {source.id}: {source.title}")
        return

    if args.command == "sources" and args.sources_command == "ingest":
        result = asyncio.run(
            build_source_ingest(container).ingest(args.source_id, force=args.force)
        )
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    if args.command == "query" and args.query_command == "ask":
        result = asyncio.run(
            build_query_agent(container).ask(
                QueryAskCommand(
                    question=" ".join(args.question),
                    mode=args.mode,
                    source_ids=args.source_ids,
                )
            )
        )
        if args.json:
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        else:
            print(result.answer)
            print(f"\nconfidence: {result.confidence}")
        return

    if args.command == "wiki":
        store = build_wiki_store(container)
        pages = store.rebuild()
        if args.wiki_command == "rebuild":
            print(f"Rebuilt wiki index for {len(pages)} pages.")
        else:
            for page in pages:
                print(f"{page.id}\t{page.page_type}\t{page.title}\t{page.path}")


if __name__ == "__main__":
    main()
