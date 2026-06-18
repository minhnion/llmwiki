import asyncio
import sqlite3

from backend.app.db.connection import SQLiteDatabase
from backend.app.db.migrations import MigrationRunner
from backend.app.domain.extraction import (
    ExtractedClaim,
    ExtractedEntity,
    ExtractedEvidence,
    ExtractedReviewItem,
    IngestExtractionResult,
)
from backend.app.domain.models import SourceRef
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.llm_client import LLMRequest, LLMResponse
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter
from backend.tests.compiler_fixtures import build_test_ingest_service


class FakeLLMClient:
    async def create_response(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="ok")

    async def extract_source(self, source: SourceRef) -> IngestExtractionResult:
        return IngestExtractionResult(
            source_title="Example Source",
            source_summary="A concise source summary.",
            source_language="English",
            document_type="markdown",
            key_takeaways=["The source introduces an LLM Wiki workflow."],
            evidence_items=[
                ExtractedEvidence(
                    locator="section: intro",
                    modality="text",
                    text="LLM Wiki keeps a persistent markdown wiki.",
                    summary="Defines the persistence idea.",
                    confidence=0.92,
                )
            ],
            claims=[
                ExtractedClaim(
                    text="LLM Wiki maintains a persistent markdown wiki.",
                    subject="LLM Wiki",
                    predicate="maintains",
                    object="persistent markdown wiki",
                    evidence_locators=["section: intro"],
                    confidence=0.9,
                    status="active",
                )
            ],
            entities=[
                ExtractedEntity(
                    name="LLM Wiki",
                    entity_type="concept",
                    aliases=["wiki llm"],
                    description="A persistent LLM-maintained knowledge base pattern.",
                    evidence_locators=["section: intro"],
                    confidence=0.88,
                )
            ],
            review_items=[
                ExtractedReviewItem(
                    review_type="scope",
                    title="Confirm intended corpus scale",
                    body="The source does not define an exact corpus size.",
                    severity="low",
                    evidence_locators=["section: intro"],
                )
            ],
            open_questions=["How will the wiki be evaluated against RAG?"],
        )


def test_ingest_source_writes_extraction_artifacts(tmp_path) -> None:
    asyncio.run(_run_ingest_source_test(tmp_path))


async def _run_ingest_source_test(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    MigrationRunner(database).run()
    source_path = tmp_path / "example.md"
    source_path.write_text("# Example\n\nLLM Wiki keeps a persistent markdown wiki.\n")
    wiki_dir = tmp_path / "wiki"
    registry = SourceRegistryService(
        source_repository=SQLiteSourceRepository(database),
        job_repository=SQLiteIngestJobRepository(database),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    )
    source = registry.register(
        RegisterSourceCommand(path=source_path, title="Example", source_type="markdown")
    )
    service = build_test_ingest_service(database, wiki_dir)

    result = await service.ingest(source.id)

    assert result.source.status == "ingested"
    assert result.coverage.coverage_status == "complete"
    assert result.graph.status == "completed"
    assert result.graph.relation_count == 3
    assert len(result.compilation.artifacts) == 2
    assert result.page.path.exists()
    page_body = result.page.path.read_text(encoding="utf-8")
    assert "## Bằng chứng" in page_body
    assert "## Artifacts" in page_body
    assert "LLM Wiki persists source-grounded knowledge artifacts." in page_body
    index_body = (wiki_dir / "index.md").read_text(encoding="utf-8")
    assert "## Nguồn tài liệu" in index_body
    assert source.id in index_body

    with sqlite3.connect(tmp_path / "app.sqlite") as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "evidence_items",
                "claims",
                "claim_evidence",
                "entities",
                "source_entities",
                "review_items",
                "wiki_pages",
                "compiler_runs",
                "compiler_passes",
                "source_manifests",
                "source_units",
                "artifacts",
                "artifact_versions",
                "artifact_evidence",
                "artifact_relations",
                "coverage_reports",
                "relation_edges",
            )
        }
        source_status = connection.execute(
            "SELECT status FROM sources WHERE id = ?",
            (source.id,),
        ).fetchone()[0]

    assert counts == {
        "evidence_items": 3,
        "claims": 3,
        "claim_evidence": 3,
        "entities": 2,
        "source_entities": 2,
        "review_items": 0,
        "wiki_pages": 3,
        "compiler_runs": 1,
        "compiler_passes": 1,
        "source_manifests": 1,
        "source_units": 3,
        "artifacts": 2,
        "artifact_versions": 2,
        "artifact_evidence": 3,
        "artifact_relations": 1,
        "coverage_reports": 1,
        "relation_edges": 3,
    }
    assert source_status == "ingested"
    with sqlite3.connect(tmp_path / "app.sqlite") as connection:
        collision_rows = connection.execute(
            """
            SELECT local_id, locator
            FROM evidence_items
            WHERE locator = 'section: concept'
            ORDER BY local_id
            """
        ).fetchall()
    assert collision_rows == [
        ("ev_rag", "section: concept"),
        ("ev_wiki", "section: concept"),
    ]
    assert "ingest | Example" in (wiki_dir / "log.md").read_text(encoding="utf-8")
    assert "compiler |" in (wiki_dir / "log.md").read_text(encoding="utf-8")
