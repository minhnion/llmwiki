import asyncio
import sqlite3

from fastapi.testclient import TestClient

from backend.app.api.routes import query as query_route
from backend.app.cli import build_parser
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
from backend.app.domain.query import (
    Citation,
    EvidenceAssessment,
    EvidenceCandidate,
    EvidenceRankingResult,
    QueryAskCommand,
    QueryPlan,
    QueryResult,
    QuerySynthesisResult,
)
from backend.app.main import create_app
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.query import SQLiteQueryRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.answer_synthesizer import AnswerSynthesizer
from backend.app.services.evidence_ranker import EvidenceRanker
from backend.app.services.llm_client import LLMRequest, LLMResponse
from backend.app.services.query_engine import QueryEngine
from backend.app.services.query_planner import QueryPlanner
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter
from backend.tests.compiler_fixtures import build_test_ingest_service


class FakeIngestLLMClient:
    async def create_response(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="ok")

    async def extract_source(self, source: SourceRef) -> IngestExtractionResult:
        return IngestExtractionResult(
            source_title="LLM Wiki vs RAG Notes",
            source_summary="Compares persistent LLM Wiki artifacts with query-time RAG.",
            source_language="English",
            document_type="markdown",
            key_takeaways=[
                "LLM Wiki persists evidence, claims, entities, and pages.",
                "Traditional RAG commonly retrieves chunks at query time.",
            ],
            evidence_items=[
                ExtractedEvidence(
                    locator="section: llm-wiki",
                    modality="text",
                    text=(
                        "LLM Wiki keeps a persistent markdown wiki with evidence, "
                        "claims, entities, and source pages."
                    ),
                    summary="Defines the persistent artifact layer in LLM Wiki.",
                    confidence=0.94,
                ),
                ExtractedEvidence(
                    locator="section: rag",
                    modality="text",
                    text=(
                        "Traditional RAG usually retrieves raw chunks at query time "
                        "and asks a model to answer from those chunks."
                    ),
                    summary="Describes the query-time retrieval pattern in traditional RAG.",
                    confidence=0.9,
                ),
            ],
            claims=[
                ExtractedClaim(
                    text="LLM Wiki persists source-grounded knowledge artifacts.",
                    subject="LLM Wiki",
                    predicate="persists",
                    object="source-grounded knowledge artifacts",
                    evidence_locators=["section: llm-wiki"],
                    confidence=0.91,
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
            ],
            entities=[
                ExtractedEntity(
                    name="LLM Wiki",
                    entity_type="concept",
                    aliases=["wiki llm"],
                    description="Persistent source-grounded knowledge base pattern.",
                    evidence_locators=["section: llm-wiki"],
                    confidence=0.92,
                ),
                ExtractedEntity(
                    name="Traditional RAG",
                    entity_type="concept",
                    aliases=["RAG"],
                    description="Retrieval augmented generation over query-time chunks.",
                    evidence_locators=["section: rag"],
                    confidence=0.89,
                ),
            ],
            review_items=[
                ExtractedReviewItem(
                    review_type="evaluation",
                    title="Compare against real RAG baselines",
                    body="The source describes a qualitative comparison but no benchmark.",
                    severity="medium",
                    evidence_locators=["section: rag"],
                )
            ],
            open_questions=["How does quality change on large heterogeneous corpora?"],
        )


class FakeQueryLLMClient:
    async def plan_query(self, command: QueryAskCommand) -> QueryPlan:
        return QueryPlan(
            rewritten_question=command.question,
            intent="compare",
            answer_language="English",
            retrieval_strategy="deep",
            keywords=[
                "LLM Wiki",
                "Traditional RAG",
                "persistent markdown wiki",
                "query time chunks",
            ],
            entity_hints=["LLM Wiki", "Traditional RAG"],
            subquestions=[
                "What does LLM Wiki persist?",
                "How does traditional RAG retrieve context?",
            ],
            must_have_evidence=["persistent", "query time"],
            source_filters=command.source_ids,
            time_filters=[],
        )

    async def rank_evidence(
        self,
        question: str,
        plan: QueryPlan,
        candidates: list[EvidenceCandidate],
        max_evidence: int,
    ) -> EvidenceRankingResult:
        selected = [candidate.evidence_id for candidate in candidates[:max_evidence]]
        return EvidenceRankingResult(
            selected_evidence_ids=selected,
            rejected_evidence_ids=[
                candidate.evidence_id
                for candidate in candidates
                if candidate.evidence_id not in selected
            ],
            assessments=[
                EvidenceAssessment(
                    evidence_id=candidate.evidence_id,
                    relevance="direct",
                    support_type="supports",
                    reason="Candidate directly discusses LLM Wiki or RAG.",
                    confidence=0.9,
                )
                for candidate in candidates[:max_evidence]
            ],
            contradictions=[],
            missing_evidence=[],
            reasoning_summary="Selected directly relevant comparison evidence.",
        )

    async def synthesize_answer(
        self,
        question: str,
        plan: QueryPlan,
        evidence: list[EvidenceCandidate],
        ranking: EvidenceRankingResult,
    ) -> QuerySynthesisResult:
        return QuerySynthesisResult(
            answer=(
                "LLM Wiki differs from traditional RAG by persisting source-grounded "
                "artifacts before query time, while traditional RAG retrieves raw "
                "chunks during the query."
            ),
            confidence="high",
            citations=[
                Citation(
                    evidence_id=candidate.evidence_id,
                    source_id=candidate.source_id,
                    source_title=candidate.source_title,
                    locator=candidate.locator,
                    quote_or_summary=candidate.summary,
                    claim_ids=candidate.claim_ids,
                )
                for candidate in evidence
            ],
            used_claim_ids=[
                claim_id
                for candidate in evidence
                for claim_id in candidate.claim_ids
            ],
            matched_entities=["LLM Wiki", "Traditional RAG"],
            contradictions=[],
            open_questions=[],
            follow_up_questions=["Evaluate answer quality against a vector RAG baseline."],
        )


def test_query_repository_searches_ingested_evidence(tmp_path) -> None:
    database, _, _ = asyncio.run(_seed_ingested_source(tmp_path))
    repository = SQLiteQueryRepository(database)
    plan = asyncio.run(
        FakeQueryLLMClient().plan_query(
            QueryAskCommand(question="How is LLM Wiki different from traditional RAG?")
        )
    )

    candidates = repository.search_evidence(
        question="How is LLM Wiki different from traditional RAG?",
        plan=plan,
        source_ids=[],
        tags=[],
        max_candidates=10,
    )

    assert len(candidates) >= 2
    assert {candidate.locator for candidate in candidates} >= {
        "section: concept",
        "section: caveat",
    }
    assert all(candidate.claim_ids for candidate in candidates)
    caveat_candidate = next(
        candidate for candidate in candidates if candidate.locator == "section: caveat"
    )
    assert "artifact_relation" in caveat_candidate.retrieval_channels


def test_query_engine_returns_grounded_answer_and_persists_trace(tmp_path) -> None:
    asyncio.run(_run_query_engine_test(tmp_path))


async def _run_query_engine_test(tmp_path) -> None:
    database, wiki_dir, source = await _seed_ingested_source(tmp_path)
    llm_client = FakeQueryLLMClient()
    engine = QueryEngine(
        repository=SQLiteQueryRepository(database),
        planner=QueryPlanner(llm_client),
        ranker=EvidenceRanker(llm_client),
        synthesizer=AnswerSynthesizer(llm_client),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    )

    result = await engine.ask(
        QueryAskCommand(
            question="How is LLM Wiki different from traditional RAG?",
            source_ids=[source.id],
            max_evidence=4,
        )
    )

    assert result.confidence == "high"
    assert result.citations
    assert result.selected_evidence
    assert "persist" in result.answer
    assert all(citation.evidence_id for citation in result.citations)

    with sqlite3.connect(database.database_path) as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM query_runs").fetchone()[0]
        citation_count = connection.execute(
            "SELECT COUNT(*) FROM query_citations"
        ).fetchone()[0]

    assert run_count == 1
    assert citation_count == len(result.citations)
    assert result.query_id in (wiki_dir / "log.md").read_text(encoding="utf-8")


def test_query_engine_returns_insufficient_when_no_evidence(tmp_path) -> None:
    asyncio.run(_run_insufficient_query_test(tmp_path))


async def _run_insufficient_query_test(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "empty.sqlite")
    wiki_dir = tmp_path / "wiki"
    MigrationRunner(database).run()
    llm_client = FakeQueryLLMClient()
    engine = QueryEngine(
        repository=SQLiteQueryRepository(database),
        planner=QueryPlanner(llm_client),
        ranker=EvidenceRanker(llm_client),
        synthesizer=AnswerSynthesizer(llm_client),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    )

    result = await engine.ask(QueryAskCommand(question="What is not in the corpus?"))

    assert result.confidence == "insufficient"
    assert result.citations == []
    assert result.candidate_count == 0
    with sqlite3.connect(database.database_path) as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM query_runs").fetchone()[0]
    assert run_count == 1


def test_ranker_does_not_force_select_irrelevant_candidates() -> None:
    class RejectingClient(FakeQueryLLMClient):
        async def rank_evidence(self, question, plan, candidates, max_evidence):
            return EvidenceRankingResult(
                selected_evidence_ids=[],
                rejected_evidence_ids=[item.evidence_id for item in candidates],
                assessments=[],
                contradictions=[],
                missing_evidence=["No direct evidence."],
                reasoning_summary="All candidates are irrelevant.",
            )

    candidate = EvidenceCandidate(
        evidence_id="ev_irrelevant",
        source_id="src_test",
        source_title="Test",
        source_path="test.md",
        wiki_page_path="",
        locator="section: other",
        modality="text",
        text="Unrelated text.",
        summary="Unrelated.",
        confidence=0.9,
        claim_ids=[],
        claims=[],
        entities=[],
        retrieval_score=1.0,
        retrieval_channels=["evidence"],
    )
    plan = asyncio.run(
        RejectingClient().plan_query(QueryAskCommand(question="A missing fact?"))
    )

    ranking = asyncio.run(
        EvidenceRanker(RejectingClient()).rank(
            "A missing fact?",
            plan,
            [candidate],
            max_evidence=4,
        )
    )

    assert ranking.selected_evidence_ids == []


def test_synthesizer_does_not_add_fallback_citation() -> None:
    class CitationlessClient(FakeQueryLLMClient):
        async def synthesize_answer(self, question, plan, evidence, ranking):
            return QuerySynthesisResult(
                answer="The evidence is insufficient.",
                confidence="high",
                citations=[],
                used_claim_ids=[],
                matched_entities=[],
                contradictions=[],
                open_questions=["Missing direct support."],
                follow_up_questions=[],
            )

    candidate = EvidenceCandidate(
        evidence_id="ev_background",
        source_id="src_test",
        source_title="Test",
        source_path="test.md",
        wiki_page_path="",
        locator="section: background",
        modality="text",
        text="Background only.",
        summary="Background.",
        confidence=0.9,
        claim_ids=[],
        claims=[],
        entities=[],
        retrieval_score=1.0,
        retrieval_channels=["evidence"],
    )
    client = CitationlessClient()
    plan = asyncio.run(client.plan_query(QueryAskCommand(question="Unsupported?")))
    ranking = EvidenceRankingResult(
        selected_evidence_ids=[candidate.evidence_id],
        rejected_evidence_ids=[],
        assessments=[],
        contradictions=[],
        missing_evidence=["Direct support."],
        reasoning_summary="Only background evidence.",
    )

    result = asyncio.run(
        AnswerSynthesizer(client).synthesize(
            "Unsupported?",
            plan,
            [candidate],
            ranking,
        )
    )

    assert result.citations == []
    assert result.confidence == "low"


def test_query_api_route_uses_query_engine(monkeypatch) -> None:
    plan = QueryPlan(
        rewritten_question="What is LLM Wiki?",
        intent="explain",
        answer_language="English",
        retrieval_strategy="fast",
        keywords=["LLM Wiki"],
        entity_hints=["LLM Wiki"],
        subquestions=[],
        must_have_evidence=[],
        source_filters=[],
        time_filters=[],
    )

    class FakeEngine:
        async def ask(self, command: QueryAskCommand) -> QueryResult:
            return QueryResult(
                query_id="qry_test",
                question=command.question,
                mode=command.mode,
                plan=plan,
                answer="LLM Wiki is a persistent source-grounded wiki.",
                confidence="high",
                citations=[],
                used_claim_ids=[],
                matched_entities=["LLM Wiki"],
                contradictions=[],
                open_questions=[],
                follow_up_questions=[],
                selected_evidence=[],
                candidate_count=0,
                created_at="2026-06-17T00:00:00+00:00",
            )

    monkeypatch.setattr(query_route, "build_query_engine", lambda container: FakeEngine())
    client = TestClient(create_app())

    response = client.post("/api/query", json={"question": "What is LLM Wiki?"})

    assert response.status_code == 200
    assert response.json()["query_id"] == "qry_test"
    assert response.json()["answer"].startswith("LLM Wiki")


def test_query_cli_parser_accepts_ask_command() -> None:
    args = build_parser().parse_args(
        ["query", "ask", "What", "is", "LLM", "Wiki?", "--mode", "fast", "--json"]
    )

    assert args.command == "query"
    assert args.query_command == "ask"
    assert args.question == ["What", "is", "LLM", "Wiki?"]
    assert args.mode == "fast"
    assert args.json is True


async def _seed_ingested_source(tmp_path):
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    wiki_dir = tmp_path / "wiki"
    MigrationRunner(database).run()
    source_path = tmp_path / "comparison.md"
    source_path.write_text(
        "# Comparison\n\nLLM Wiki persists artifacts. RAG retrieves chunks.\n",
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
            title="LLM Wiki vs RAG Notes",
            source_type="markdown",
            tags=("comparison",),
        )
    )
    service = build_test_ingest_service(database, wiki_dir)
    await service.ingest(source.id)
    return database, wiki_dir, source
