import argparse
import asyncio
import json
from pathlib import Path

from backend.app.api.routes.graph import build_graph_builder
from backend.app.api.routes.query import build_query_engine
from backend.app.application.container import get_container
from backend.app.db.migrations import MigrationRunner
from backend.app.domain.graph import GraphBuildCommand
from backend.app.domain.query import QueryAskCommand
from backend.app.repositories.extractions import SQLiteExtractionRepository
from backend.app.repositories.graph import SQLiteGraphRepository
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

    query_parser = subparsers.add_parser("query")
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)
    ask_parser = query_subparsers.add_parser("ask")
    ask_parser.add_argument("question", nargs="+")
    ask_parser.add_argument("--mode", default="deep")
    ask_parser.add_argument("--source-id", dest="source_ids", action="append", default=[])
    ask_parser.add_argument("--tag", dest="tags", action="append", default=[])
    ask_parser.add_argument("--max-candidates", type=int, default=24)
    ask_parser.add_argument("--max-evidence", type=int, default=8)
    ask_parser.add_argument("--json", action="store_true")

    graph_parser = subparsers.add_parser("graph")
    graph_subparsers = graph_parser.add_subparsers(dest="graph_command", required=True)
    graph_build_parser = graph_subparsers.add_parser("build")
    graph_build_parser.add_argument("--source-id", dest="source_ids", action="append", default=[])
    graph_build_parser.add_argument("--no-rebuild", dest="rebuild", action="store_false")
    graph_build_parser.add_argument("--max-claims-per-batch", type=int, default=40)
    graph_build_parser.add_argument("--json", action="store_true")
    graph_inspect_parser = graph_subparsers.add_parser("inspect")
    graph_inspect_parser.add_argument("entity")
    graph_inspect_parser.add_argument("--json", action="store_true")
    graph_search_parser = graph_subparsers.add_parser("search")
    graph_search_parser.add_argument("query", nargs="+")
    graph_search_parser.add_argument("--json", action="store_true")
    graph_contradictions_parser = graph_subparsers.add_parser("contradictions")
    graph_contradictions_parser.add_argument("--status", default="open")
    graph_contradictions_parser.add_argument("--json", action="store_true")

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

    if args.command == "query" and args.query_command == "ask":
        MigrationRunner(container.database).run()
        if not container.settings.openai_api_key:
            raise SystemExit("OPENAI_API_KEY is required for query synthesis.")
        command = QueryAskCommand(
            question=" ".join(args.question),
            mode=args.mode,
            source_ids=args.source_ids,
            tags=args.tags,
            max_candidates=args.max_candidates,
            max_evidence=args.max_evidence,
        )
        result = asyncio.run(build_query_engine(container).ask(command))
        if args.json:
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
            return
        print(result.answer)
        print(f"\nconfidence: {result.confidence}")
        print(f"query_id: {result.query_id}")
        if result.citations:
            print("\ncitations:")
            for citation in result.citations:
                print(
                    f"- {citation.source_title} | {citation.locator} | "
                    f"{citation.evidence_id}"
                )
        return

    if args.command == "graph" and args.graph_command == "build":
        MigrationRunner(container.database).run()
        if not container.settings.openai_api_key:
            raise SystemExit("OPENAI_API_KEY is required for graph build.")
        result = asyncio.run(
            build_graph_builder(container).build(
                GraphBuildCommand(
                    source_ids=args.source_ids,
                    rebuild=args.rebuild,
                    max_claims_per_batch=args.max_claims_per_batch,
                )
            )
        )
        if args.json:
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
            return
        print(f"Graph build {result.status}: {result.graph_run_id}")
        print(f"claims: {result.claim_count}")
        print(f"relations: {result.relation_count}")
        print(f"contradictions: {result.contradiction_count}")
        print(f"merge_candidates: {result.merge_candidate_count}")
        print(f"entity_pages: {result.entity_page_count}")
        return

    if args.command == "graph" and args.graph_command == "inspect":
        MigrationRunner(container.database).run()
        detail = SQLiteGraphRepository(container.database).get_entity_detail(args.entity)
        if detail is None:
            raise SystemExit(f"Entity not found: {args.entity}")
        if args.json:
            print(json.dumps(detail.model_dump(), ensure_ascii=False, indent=2))
            return
        print(f"{detail.entity.canonical_name} ({detail.entity.entity_type})")
        print(detail.entity.description)
        print(f"outgoing_relations: {len(detail.outgoing_relations)}")
        print(f"incoming_relations: {len(detail.incoming_relations)}")
        if detail.page_path:
            print(f"page: {detail.page_path}")
        return

    if args.command == "graph" and args.graph_command == "search":
        MigrationRunner(container.database).run()
        result = SQLiteGraphRepository(container.database).search_graph(" ".join(args.query))
        if args.json:
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
            return
        print("entities:")
        for entity in result.entities:
            print(f"- {entity.canonical_name} ({entity.entity_type}) [{entity.entity_id}]")
        print("relations:")
        for relation in result.relations:
            print(
                f"- {relation.subject_name} {relation.predicate} "
                f"{relation.object_value} [{relation.id}]"
            )
        return

    if args.command == "graph" and args.graph_command == "contradictions":
        MigrationRunner(container.database).run()
        contradictions = SQLiteGraphRepository(container.database).list_contradictions(
            args.status
        )
        if args.json:
            print(
                json.dumps(
                    [contradiction.model_dump() for contradiction in contradictions],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        for contradiction in contradictions:
            print(
                f"- {contradiction.relationship} "
                f"{contradiction.claim_a_id} <-> {contradiction.claim_b_id} "
                f"(confidence {contradiction.confidence:.2f})"
            )
        return

    parser.error("Unsupported command")


if __name__ == "__main__":
    main()
