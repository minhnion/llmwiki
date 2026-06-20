import asyncio
import sqlite3

from backend.app.api.routes import graph as graph_route
from backend.app.cli import build_parser
from backend.app.db.connection import SQLiteDatabase
from backend.app.db.migrations import MigrationRunner
from backend.app.domain.extraction import (
    ExtractedClaim,
    ExtractedEntity,
    ExtractedEvidence,
    IngestExtractionResult,
)
from backend.app.domain.graph import (
    ClaimGraphContext,
    ContradictionDetectionResult,
    ExtractedContradiction,
    ExtractedRelation,
    GraphBuildCommand,
    GraphBuildResult,
    GraphExtractionResult,
)
from backend.app.domain.models import SourceRef
from backend.app.domain.query import QueryPlan
from backend.app.repositories.graph import SQLiteGraphRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.query import SQLiteQueryRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.contradiction_detector import ContradictionDetector
from backend.app.services.entity_page_writer import EntityPageWriter
from backend.app.services.graph_builder import GraphBuilder
from backend.app.services.graph_extractor import GraphExtractor
from backend.app.services.llm_client import LLMRequest, LLMResponse
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter
from backend.tests.compiler_fixtures import build_test_ingest_service


class FakeIngestLLMClient:
    async def create_response(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="ok")

    async def extract_source(self, source: SourceRef) -> IngestExtractionResult:
        return IngestExtractionResult(
            source_title="Graph Notes",
            source_summary="Contains comparison claims for graph extraction.",
            source_language="English",
            document_type="markdown",
            key_takeaways=["LLM Wiki persists artifacts.", "RAG retrieves chunks."],
            evidence_items=[
                ExtractedEvidence(
                    locator="section: wiki",
                    modality="text",
                    text="LLM Wiki persists source-grounded knowledge artifacts.",
                    summary="Supports persistence relation.",
                    confidence=0.94,
                ),
                ExtractedEvidence(
                    locator="section: rag",
                    modality="text",
                    text="Traditional RAG retrieves raw chunks at query time.",
                    summary="Supports retrieval relation.",
                    confidence=0.9,
                ),
                ExtractedEvidence(
                    locator="section: caveat",
                    modality="text",
                    text="LLM Wiki does not persist generated pages in this variant.",
                    summary="Conflicts with the persistence claim.",
                    confidence=0.86,
                ),
            ],
            claims=[
                ExtractedClaim(
                    text="LLM Wiki persists source-grounded knowledge artifacts.",
                    subject="LLM Wiki",
                    predicate="persists",
                    object="source-grounded knowledge artifacts",
                    evidence_locators=["section: wiki"],
                    confidence=0.92,
                    status="active",
                ),
                ExtractedClaim(
                    text="Traditional RAG retrieves raw chunks at query time.",
                    subject="Traditional RAG",
                    predicate="retrieves",
                    object="raw chunks at query time",
                    evidence_locators=["section: rag"],
                    confidence=0.88,
                    status="active",
                ),
                ExtractedClaim(
                    text="LLM Wiki does not persist generated pages in this variant.",
                    subject="LLM Wiki",
                    predicate="does not persist",
                    object="generated pages",
                    evidence_locators=["section: caveat"],
                    confidence=0.82,
                    status="active",
                ),
            ],
            entities=[
                ExtractedEntity(
                    name="LLM Wiki",
                    entity_type="concept",
                    aliases=["Wiki LLM"],
                    description="Persistent source-grounded wiki pattern.",
                    evidence_locators=["section: wiki"],
                    confidence=0.92,
                ),
                ExtractedEntity(
                    name="Traditional RAG",
                    entity_type="concept",
                    aliases=["RAG"],
                    description="Query-time retrieval augmented generation pattern.",
                    evidence_locators=["section: rag"],
                    confidence=0.89,
                ),
            ],
            review_items=[],
            open_questions=[],
        )


class FakeGraphLLMClient:
    async def extract_graph_relations(
        self,
        claims: list[ClaimGraphContext],
    ) -> GraphExtractionResult:
        relations = []
        for claim in claims:
            if not claim.evidence:
                continue
            relations.append(
                ExtractedRelation(
                    subject=claim.subject,
                    predicate=claim.predicate,
                    object=claim.object,
                    object_type="text",
                    claim_id=claim.claim_id,
                    evidence_id=claim.evidence[0].evidence_id,
                    confidence=claim.confidence,
                    status=claim.status,
                    qualifiers=[],
                )
            )
        return GraphExtractionResult(
            relations=relations,
            entity_merge_candidates=[],
            notes=[],
        )

    async def detect_contradictions(
        self,
        claims: list[ClaimGraphContext],
    ) -> ContradictionDetectionResult:
        persist_claim = next(
            (claim for claim in claims if claim.predicate == "persists"),
            None,
        )
        negative_claim = next(
            (claim for claim in claims if "does not" in claim.predicate),
            None,
        )
        if persist_claim is None or negative_claim is None:
            return ContradictionDetectionResult(contradictions=[], notes=[])
        return ContradictionDetectionResult(
            contradictions=[
                ExtractedContradiction(
                    claim_a_id=persist_claim.claim_id,
                    claim_b_id=negative_claim.claim_id,
                    relationship="contradicts",
                    reason=(
                        "One claim says LLM Wiki persists artifacts; "
                        "the other denies persistence."
                    ),
                    confidence=0.87,
                    evidence_ids=[
                        persist_claim.evidence[0].evidence_id,
                        negative_claim.evidence[0].evidence_id,
                    ],
                )
            ],
            notes=[],
        )


def test_graph_build_persists_relations_contradictions_and_entity_pages(tmp_path) -> None:
    asyncio.run(_run_graph_build_test(tmp_path))


async def _run_graph_build_test(tmp_path) -> None:
    database, wiki_dir, _ = await _seed_ingested_source(tmp_path)
    llm_client = FakeGraphLLMClient()
    builder = GraphBuilder(
        repository=SQLiteGraphRepository(database),
        extractor=GraphExtractor(llm_client),
        contradiction_detector=ContradictionDetector(llm_client),
        entity_page_writer=EntityPageWriter(wiki_dir),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    )

    result = await builder.build(GraphBuildCommand())

    assert result.status == "completed"
    assert result.claim_count == 3
    assert result.relation_count == 3
    assert result.contradiction_count == 1
    assert result.entity_page_count == 2

    repository = SQLiteGraphRepository(database)
    detail = repository.get_entity_detail("LLM Wiki")
    assert detail is not None
    assert len(detail.outgoing_relations) == 2
    assert detail.page_path is not None
    assert "LLM Wiki" in (wiki_dir / detail.page_path).read_text(encoding="utf-8")
    contradictions = repository.list_contradictions()
    assert len(contradictions) == 1
    assert contradictions[0].relationship == "contradicts"
    search = repository.search_graph("source-grounded artifacts")
    assert search.relations
    visualization = repository.visualize_graph(limit=10)
    assert visualization.nodes
    assert visualization.edges
    assert any(edge.label == "persists" for edge in visualization.edges)

    with sqlite3.connect(database.database_path) as connection:
        relation_count = connection.execute("SELECT COUNT(*) FROM relation_edges").fetchone()[0]
        run_count = connection.execute("SELECT COUNT(*) FROM graph_runs").fetchone()[0]
        resolved_subjects = connection.execute(
            "SELECT COUNT(*) FROM relation_edges WHERE subject_entity_id IS NOT NULL"
        ).fetchone()[0]

    assert relation_count == 3
    assert resolved_subjects == 3
    assert run_count == 2
    assert result.graph_run_id in (wiki_dir / "log.md").read_text(encoding="utf-8")


def test_query_retrieval_uses_graph_channel_after_graph_build(tmp_path) -> None:
    asyncio.run(_run_graph_query_expansion_test(tmp_path))


async def _run_graph_query_expansion_test(tmp_path) -> None:
    database, wiki_dir, _ = await _seed_ingested_source(tmp_path)
    llm_client = FakeGraphLLMClient()
    await GraphBuilder(
        repository=SQLiteGraphRepository(database),
        extractor=GraphExtractor(llm_client),
        contradiction_detector=ContradictionDetector(llm_client),
        entity_page_writer=EntityPageWriter(wiki_dir),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    ).build(GraphBuildCommand())
    plan = QueryPlan(
        rewritten_question="What persists source-grounded artifacts?",
        intent="fact",
        answer_language="English",
        retrieval_strategy="deep",
        keywords=["source-grounded artifacts"],
        entity_hints=["LLM Wiki"],
        subquestions=[],
        must_have_evidence=[],
        source_filters=[],
        time_filters=[],
    )

    candidates = SQLiteQueryRepository(database).search_evidence(
        question="What persists source-grounded artifacts?",
        plan=plan,
        source_ids=[],
        tags=[],
        max_candidates=8,
    )

    assert candidates
    assert any("graph" in candidate.retrieval_channels for candidate in candidates)


def test_graph_api_build_route_uses_builder(monkeypatch) -> None:
    class FakeBuilder:
        async def build(self, command: GraphBuildCommand) -> GraphBuildResult:
            return GraphBuildResult(
                graph_run_id="grun_test",
                source_ids=command.source_ids,
                claim_count=1,
                relation_count=1,
                contradiction_count=0,
                merge_candidate_count=0,
                entity_page_count=1,
                status="completed",
                started_at="2026-06-17T00:00:00+00:00",
                finished_at="2026-06-17T00:00:01+00:00",
            )

    monkeypatch.setattr(graph_route, "build_graph_builder", lambda container: FakeBuilder())

    response = asyncio.run(
        graph_route.build_graph(
            GraphBuildCommand(source_ids=["src_test"]),
            container=object(),
        )
    )

    assert response.graph_run_id == "grun_test"
    assert response.source_ids == ["src_test"]


def test_graph_visualization_api_returns_nodes_and_edges(tmp_path) -> None:
    asyncio.run(_run_graph_visualization_api_test(tmp_path))


async def _run_graph_visualization_api_test(tmp_path) -> None:
    database, wiki_dir, _ = await _seed_ingested_source(tmp_path)
    llm_client = FakeGraphLLMClient()
    await GraphBuilder(
        repository=SQLiteGraphRepository(database),
        extractor=GraphExtractor(llm_client),
        contradiction_detector=ContradictionDetector(llm_client),
        entity_page_writer=EntityPageWriter(wiki_dir),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    ).build(GraphBuildCommand())
    response = graph_route.visualize_graph(
        container=type("Container", (), {"database": database})(),
        q=None,
        limit=10,
    )

    assert response.nodes
    assert response.edges
    assert any(edge.label == "persists" for edge in response.edges)


def test_graph_cli_parser_accepts_commands() -> None:
    build_args = build_parser().parse_args(
        ["graph", "build", "--source-id", "src_test", "--json"]
    )
    inspect_args = build_parser().parse_args(["graph", "inspect", "LLM Wiki"])

    assert build_args.command == "graph"
    assert build_args.graph_command == "build"
    assert build_args.source_ids == ["src_test"]
    assert build_args.json is True
    assert inspect_args.graph_command == "inspect"
    assert inspect_args.entity == "LLM Wiki"


async def _seed_ingested_source(tmp_path):
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    wiki_dir = tmp_path / "wiki"
    MigrationRunner(database).run()
    source_path = tmp_path / "graph.md"
    source_path.write_text(
        "# Graph\n\nLLM Wiki persists artifacts. RAG retrieves chunks.\n",
        encoding="utf-8",
    )
    registry = SourceRegistryService(
        source_repository=SQLiteSourceRepository(database),
        job_repository=SQLiteIngestJobRepository(database),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    )
    source = registry.register(
        RegisterSourceCommand(
            path=source_path,
            title="Graph Notes",
            source_type="markdown",
            tags=("graph",),
        )
    )
    await build_test_ingest_service(
        database,
        wiki_dir,
        graph_client=FakeGraphLLMClient(),
    ).ingest(source.id)
    return database, wiki_dir, source
