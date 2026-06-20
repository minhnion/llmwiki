from backend.app.db.connection import SQLiteDatabase
from backend.app.domain.compiler import (
    ArtifactStatement,
    CompilationBundle,
    CompilationPassPlan,
    CompilationPassResult,
    CompiledArtifact,
    CompiledDetailCoverage,
    CompiledEvidence,
    CompiledRelation,
    CompiledSemanticNode,
    CoverageDetailAssessment,
    CoverageReport,
    CoverageUnitAssessment,
    KnowledgeLens,
    ObservedDetail,
    OpenMetadataItem,
    SourceLocator,
    SourceManifest,
    SourceProfile,
    SourceUnit,
    StatementReference,
    WikiIntegrationPlan,
    WikiPagePlan,
)
from backend.app.domain.graph import (
    ClaimGraphContext,
    ContradictionDetectionResult,
    ExtractedRelation,
    GraphExtractionResult,
)
from backend.app.domain.models import SourceRef
from backend.app.repositories.compiler import SQLiteCompilerRepository
from backend.app.repositories.extractions import SQLiteExtractionRepository
from backend.app.repositories.graph import SQLiteGraphRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.repositories.wiki import SQLiteWikiRepository
from backend.app.services.contradiction_detector import ContradictionDetector
from backend.app.services.entity_page_writer import EntityPageWriter
from backend.app.services.graph_builder import GraphBuilder
from backend.app.services.graph_extractor import GraphExtractor
from backend.app.services.knowledge_page_writer import KnowledgePageWriter
from backend.app.services.source_ingest import SourceIngestService
from backend.app.services.source_page_writer import SourcePageWriter
from backend.app.services.wiki_log import WikiLogWriter


class FakeCompilerClient:
    def __init__(self, coverage_reports: list[CoverageReport] | None = None) -> None:
        self.coverage_reports = coverage_reports or [_complete_coverage()]
        self.compilation_calls: list[str] = []
        self.audit_calls = 0

    async def profile_source(self, source: SourceRef) -> SourceManifest:
        return SourceManifest(
            source_id=source.id,
            language="English",
            document_profile=SourceProfile(
                kind=source.source_type,
                summary="Contains comparison claims for compiler and graph tests.",
                modalities=["text"],
                confidence=0.95,
            ),
            content_units=[
                SourceUnit(
                    local_id="unit_wiki",
                    label="Wiki",
                    locator=_locator("section", "concept"),
                    summary="Persistent wiki concept.",
                    importance=0.95,
                ),
                SourceUnit(
                    local_id="unit_rag",
                    label="RAG",
                    locator=_locator("section", "concept"),
                    summary="RAG retrieval concept.",
                    importance=0.9,
                ),
                SourceUnit(
                    local_id="unit_caveat",
                    label="Caveat",
                    locator=_locator("section", "caveat"),
                    summary="Persistence caveat.",
                    importance=0.8,
                ),
            ],
            observed_details=[
                ObservedDetail(
                    local_id="detail_wiki",
                    source_unit_id="unit_wiki",
                    detail_kind="architectural_property",
                    description="LLM Wiki persists source-grounded knowledge artifacts.",
                    locator=_locator("section", "concept"),
                    importance=0.95,
                    query_hint="persistent source-grounded knowledge artifacts",
                ),
                ObservedDetail(
                    local_id="detail_rag",
                    source_unit_id="unit_rag",
                    detail_kind="retrieval_behavior",
                    description="Traditional RAG retrieves raw chunks at query time.",
                    locator=_locator("section", "concept"),
                    importance=0.9,
                    query_hint="query-time raw chunk retrieval",
                ),
                ObservedDetail(
                    local_id="detail_caveat",
                    source_unit_id="unit_caveat",
                    detail_kind="qualification",
                    description="This variant does not persist generated pages.",
                    locator=_locator("section", "caveat"),
                    importance=0.8,
                    query_hint="persistence caveat for generated pages",
                ),
            ],
            candidate_knowledge_lenses=[
                KnowledgeLens(
                    name="architecture comparison",
                    reason="The source compares knowledge architectures.",
                    priority=0.95,
                )
            ],
            compilation_plan=[
                CompilationPassPlan(
                    pass_id="pass_core",
                    objective="Compile core concepts and claims.",
                    target_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
                    target_detail_ids=[
                        "detail_wiki",
                        "detail_rag",
                        "detail_caveat",
                    ],
                    expected_outputs=["evidence", "concept artifacts", "relations"],
                )
            ],
        )

    async def compile_source_pass(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        plan: CompilationPassPlan,
        existing: CompilationBundle,
    ) -> CompilationPassResult:
        self.compilation_calls.append(plan.pass_id)
        if plan.pass_id not in {"pass_core", "primary_full_source_compile"}:
            return _follow_up_result(plan)
        return CompilationPassResult(
            pass_id=plan.pass_id,
            ledger_items=list(manifest.observed_details),
            evidence_items=[
                CompiledEvidence(
                    local_id="ev_wiki",
                    source_unit_ids=["unit_wiki"],
                    locator=_locator("section", "concept"),
                    modality="text",
                    content="LLM Wiki persists source-grounded knowledge artifacts.",
                    summary="Supports persistence.",
                    confidence=0.94,
                ),
                CompiledEvidence(
                    local_id="ev_rag",
                    source_unit_ids=["unit_rag"],
                    locator=_locator("section", "concept"),
                    modality="text",
                    content="Traditional RAG retrieves raw chunks at query time.",
                    summary="Supports query-time retrieval.",
                    confidence=0.91,
                ),
                CompiledEvidence(
                    local_id="ev_caveat",
                    source_unit_ids=["unit_caveat"],
                    locator=_locator("section", "caveat"),
                    modality="text",
                    content="This variant does not persist generated pages.",
                    summary="Qualifies persistence.",
                    confidence=0.84,
                ),
            ],
            artifacts=[
                CompiledArtifact(
                    local_id="art_wiki",
                    artifact_type="concept",
                    title="LLM Wiki",
                    summary="A persistent source-grounded knowledge pattern.",
                    content="LLM Wiki compiles sources into persistent artifacts.",
                    aliases=["Wiki LLM"],
                    scope=[],
                    evidence_local_ids=["ev_wiki", "ev_caveat"],
                    source_unit_ids=["unit_wiki", "unit_caveat"],
                    related_artifact_local_ids=["art_rag"],
                    statements=[
                        ArtifactStatement(
                            local_id="stmt_wiki_persists",
                            statement_type="fact",
                            text="LLM Wiki persists source-grounded knowledge artifacts.",
                            subject="LLM Wiki",
                            predicate="persists",
                            object="source-grounded knowledge artifacts",
                            object_type="concept",
                            evidence_local_ids=["ev_wiki"],
                            source_unit_ids=["unit_wiki"],
                            qualifiers=[],
                            confidence=0.92,
                            status="active",
                        ),
                        ArtifactStatement(
                            local_id="stmt_wiki_caveat",
                            statement_type="qualification",
                            text="This LLM Wiki variant does not persist generated pages.",
                            subject="LLM Wiki",
                            predicate="does not persist",
                            object="generated pages",
                            object_type="concept",
                            evidence_local_ids=["ev_caveat"],
                            source_unit_ids=["unit_caveat"],
                            qualifiers=[],
                            confidence=0.82,
                            status="active",
                        ),
                    ],
                    confidence=0.92,
                    status="active",
                    review_status="unreviewed",
                    metadata=[],
                ),
                CompiledArtifact(
                    local_id="art_rag",
                    artifact_type="concept",
                    title="Traditional RAG",
                    summary="A query-time raw chunk retrieval pattern.",
                    content="Traditional RAG retrieves raw chunks during a query.",
                    aliases=["RAG"],
                    scope=[],
                    evidence_local_ids=["ev_rag"],
                    source_unit_ids=["unit_rag"],
                    related_artifact_local_ids=["art_wiki"],
                    statements=[
                        ArtifactStatement(
                            local_id="stmt_rag_retrieves",
                            statement_type="fact",
                            text="Traditional RAG retrieves raw chunks at query time.",
                            subject="Traditional RAG",
                            predicate="retrieves",
                            object="raw chunks at query time",
                            object_type="concept",
                            evidence_local_ids=["ev_rag"],
                            source_unit_ids=["unit_rag"],
                            qualifiers=[],
                            confidence=0.89,
                            status="active",
                        )
                    ],
                    confidence=0.9,
                    status="active",
                    review_status="unreviewed",
                    metadata=[],
                ),
            ],
            semantic_nodes=[
                CompiledSemanticNode(
                    local_id="node_llm_wiki",
                    name="LLM Wiki",
                    node_type="concept",
                    aliases=["Wiki LLM"],
                    description="Persistent source-grounded wiki pattern.",
                    evidence_local_ids=["ev_wiki"],
                    source_unit_ids=["unit_wiki"],
                    confidence=0.92,
                    status="active",
                ),
                CompiledSemanticNode(
                    local_id="node_rag",
                    name="Traditional RAG",
                    node_type="concept",
                    aliases=["RAG"],
                    description="Query-time retrieval pattern.",
                    evidence_local_ids=["ev_rag"],
                    source_unit_ids=["unit_rag"],
                    confidence=0.9,
                    status="active",
                ),
            ],
            relations=[
                CompiledRelation(
                    source_artifact_local_id="art_wiki",
                    target_artifact_local_id="art_rag",
                    target_literal="",
                    relation_type="contrasts_with",
                    evidence_local_ids=["ev_wiki", "ev_rag"],
                    qualifiers=[
                        OpenMetadataItem(key="scope", value="knowledge persistence")
                    ],
                    confidence=0.9,
                    status="active",
                )
            ],
            detail_coverage=[
                CompiledDetailCoverage(
                    detail_id="detail_wiki",
                    status="covered",
                    evidence_local_ids=["ev_wiki"],
                    artifact_local_ids=["art_wiki"],
                    statement_refs=[
                        StatementReference(
                            artifact_local_id="art_wiki",
                            statement_local_id="stmt_wiki_persists",
                        )
                    ],
                    notes="Detail is represented by a direct statement.",
                    confidence=0.92,
                ),
                CompiledDetailCoverage(
                    detail_id="detail_rag",
                    status="covered",
                    evidence_local_ids=["ev_rag"],
                    artifact_local_ids=["art_rag"],
                    statement_refs=[
                        StatementReference(
                            artifact_local_id="art_rag",
                            statement_local_id="stmt_rag_retrieves",
                        )
                    ],
                    notes="Detail is represented by a direct statement.",
                    confidence=0.9,
                ),
                CompiledDetailCoverage(
                    detail_id="detail_caveat",
                    status="covered",
                    evidence_local_ids=["ev_caveat"],
                    artifact_local_ids=["art_wiki"],
                    statement_refs=[
                        StatementReference(
                            artifact_local_id="art_wiki",
                            statement_local_id="stmt_wiki_caveat",
                        )
                    ],
                    notes="Detail is represented by a qualifying statement.",
                    confidence=0.82,
                ),
            ],
            review_items=[],
            covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
            notes=[],
        )

    async def audit_compilation(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        compilation: CompilationBundle,
        iteration: int,
    ) -> CoverageReport:
        report = self.coverage_reports[min(self.audit_calls, len(self.coverage_reports) - 1)]
        self.audit_calls += 1
        return report

    async def plan_wiki_integration(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        compilation: CompilationBundle,
    ) -> WikiIntegrationPlan:
        return WikiIntegrationPlan(
            pages=[
                WikiPagePlan(
                    local_id="page_wiki",
                    title="LLM Wiki",
                    page_type="concept",
                    summary="Persistent source-grounded knowledge pattern.",
                    artifact_local_ids=["art_wiki"],
                    related_page_local_ids=["page_rag"],
                    confidence=0.92,
                    review_status="unreviewed",
                ),
                WikiPagePlan(
                    local_id="page_rag",
                    title="Traditional RAG",
                    page_type="concept",
                    summary="Query-time raw chunk retrieval pattern.",
                    artifact_local_ids=["art_rag"],
                    related_page_local_ids=["page_wiki"],
                    confidence=0.9,
                    review_status="unreviewed",
                ),
            ],
            notes=[],
        )


class FakeGraphClient:
    async def extract_graph_relations(
        self,
        claims: list[ClaimGraphContext],
    ) -> GraphExtractionResult:
        return GraphExtractionResult(
            relations=[
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
                for claim in claims
                if claim.evidence
            ],
            entity_merge_candidates=[],
            notes=[],
        )

    async def detect_contradictions(
        self,
        claims: list[ClaimGraphContext],
    ) -> ContradictionDetectionResult:
        return ContradictionDetectionResult(contradictions=[], notes=[])


def build_test_ingest_service(
    database: SQLiteDatabase,
    wiki_dir,
    compiler_client: FakeCompilerClient | None = None,
    graph_client=None,
) -> SourceIngestService:
    graph_llm = graph_client or FakeGraphClient()
    return SourceIngestService(
        source_repository=SQLiteSourceRepository(database),
        compiler_repository=SQLiteCompilerRepository(database),
        extraction_repository=SQLiteExtractionRepository(database),
        job_repository=SQLiteIngestJobRepository(database),
        llm_client=compiler_client or FakeCompilerClient(),
        graph_builder=GraphBuilder(
            repository=SQLiteGraphRepository(database),
            extractor=GraphExtractor(graph_llm),
            contradiction_detector=ContradictionDetector(graph_llm),
            entity_page_writer=EntityPageWriter(wiki_dir),
            wiki_log_writer=WikiLogWriter(wiki_dir),
        ),
        source_page_writer=SourcePageWriter(wiki_dir),
        knowledge_page_writer=KnowledgePageWriter(wiki_dir),
        wiki_repository=SQLiteWikiRepository(database),
        wiki_log_writer=WikiLogWriter(wiki_dir),
        max_file_bytes=50_000_000,
        model="fake-model",
        compiler_version="knowledge-compiler-v2-test",
        prompt_version="compiler-prompts-v2-test",
        schema_version="compiler-schema-v2-test",
    )


def _locator(kind: str, value: str) -> SourceLocator:
    return SourceLocator(kind=kind, value=value, metadata=[])


def _complete_coverage() -> CoverageReport:
    return CoverageReport(
        coverage_status="complete",
        covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit_id,
                status="complete",
                represented_knowledge=["Core knowledge represented."],
                missing_knowledge=[],
                confidence=0.94,
            )
            for unit_id in ["unit_wiki", "unit_rag", "unit_caveat"]
        ],
        detail_assessments=[
            CoverageDetailAssessment(
                detail_id="detail_wiki",
                unit_id="unit_wiki",
                status="covered",
                represented_knowledge=["LLM Wiki persistence is represented."],
                missing_knowledge=[],
                evidence_local_ids=["ev_wiki"],
                artifact_local_ids=["art_wiki"],
                statement_refs=[
                    StatementReference(
                        artifact_local_id="art_wiki",
                        statement_local_id="stmt_wiki_persists",
                    )
                ],
                confidence=0.94,
            ),
            CoverageDetailAssessment(
                detail_id="detail_rag",
                unit_id="unit_rag",
                status="covered",
                represented_knowledge=["RAG retrieval behavior is represented."],
                missing_knowledge=[],
                evidence_local_ids=["ev_rag"],
                artifact_local_ids=["art_rag"],
                statement_refs=[
                    StatementReference(
                        artifact_local_id="art_rag",
                        statement_local_id="stmt_rag_retrieves",
                    )
                ],
                confidence=0.94,
            ),
            CoverageDetailAssessment(
                detail_id="detail_caveat",
                unit_id="unit_caveat",
                status="covered",
                represented_knowledge=["The persistence caveat is represented."],
                missing_knowledge=[],
                evidence_local_ids=["ev_caveat"],
                artifact_local_ids=["art_wiki"],
                statement_refs=[
                    StatementReference(
                        artifact_local_id="art_wiki",
                        statement_local_id="stmt_wiki_caveat",
                    )
                ],
                confidence=0.9,
            ),
        ],
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.94,
    )


def _follow_up_result(plan: CompilationPassPlan) -> CompilationPassResult:
    target_units = plan.target_unit_ids or ["unit_follow_up"]
    ledger_ids = plan.target_detail_ids or [
        f"ledger_{unit_id}" for unit_id in plan.target_unit_ids
    ]
    ledger_items = [
        ObservedDetail(
            local_id=detail_id,
            source_unit_id=target_units[min(index, len(target_units) - 1)],
            detail_kind="follow_up_check",
            description=f"Follow-up coverage check for {detail_id}.",
            locator=_locator("section", detail_id),
            importance=0.5,
            query_hint=f"follow-up {detail_id}",
        )
        for index, detail_id in enumerate(ledger_ids)
    ]
    return CompilationPassResult(
        pass_id=plan.pass_id,
        ledger_items=ledger_items,
        evidence_items=[],
        artifacts=[],
        semantic_nodes=[],
        relations=[],
        detail_coverage=[
            CompiledDetailCoverage(
                detail_id=item.local_id,
                status="missing",
                evidence_local_ids=[],
                artifact_local_ids=[],
                statement_refs=[],
                notes="Synthetic follow-up fixture ledger item.",
                confidence=0.0,
            )
            for item in ledger_items
        ],
        review_items=[],
        covered_unit_ids=plan.target_unit_ids,
        notes=["Follow-up pass completed."],
    )
