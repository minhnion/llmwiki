from backend.app.db.connection import SQLiteDatabase
from backend.app.domain.compiler import (
    ArtifactStatement,
    CompilationBundle,
    CompilationPassPlan,
    CompilationPassResult,
    CompiledArtifact,
    CompiledEvidence,
    CompiledRelation,
    CoverageReport,
    CoverageUnitAssessment,
    KnowledgeLens,
    OpenMetadataItem,
    SourceLocator,
    SourceManifest,
    SourceProfile,
    SourceUnit,
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
from backend.app.services.contradiction_detector import ContradictionDetector
from backend.app.services.entity_page_writer import EntityPageWriter
from backend.app.services.graph_builder import GraphBuilder
from backend.app.services.graph_extractor import GraphExtractor
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
        if plan.pass_id != "pass_core":
            return _follow_up_result(plan)
        return CompilationPassResult(
            pass_id=plan.pass_id,
            evidence_items=[
                CompiledEvidence(
                    local_id="ev_wiki",
                    locator=_locator("section", "concept"),
                    modality="text",
                    content="LLM Wiki persists source-grounded knowledge artifacts.",
                    summary="Supports persistence.",
                    confidence=0.94,
                ),
                CompiledEvidence(
                    local_id="ev_rag",
                    locator=_locator("section", "concept"),
                    modality="text",
                    content="Traditional RAG retrieves raw chunks at query time.",
                    summary="Supports query-time retrieval.",
                    confidence=0.91,
                ),
                CompiledEvidence(
                    local_id="ev_caveat",
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
                    related_artifact_local_ids=["art_rag"],
                    statements=[
                        ArtifactStatement(
                            text="LLM Wiki persists source-grounded knowledge artifacts.",
                            subject="LLM Wiki",
                            predicate="persists",
                            object="source-grounded knowledge artifacts",
                            evidence_local_ids=["ev_wiki"],
                            confidence=0.92,
                            status="active",
                        ),
                        ArtifactStatement(
                            text="This LLM Wiki variant does not persist generated pages.",
                            subject="LLM Wiki",
                            predicate="does not persist",
                            object="generated pages",
                            evidence_local_ids=["ev_caveat"],
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
                    related_artifact_local_ids=["art_wiki"],
                    statements=[
                        ArtifactStatement(
                            text="Traditional RAG retrieves raw chunks at query time.",
                            subject="Traditional RAG",
                            predicate="retrieves",
                            object="raw chunks at query time",
                            evidence_local_ids=["ev_rag"],
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
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.94,
    )


def _follow_up_result(plan: CompilationPassPlan) -> CompilationPassResult:
    return CompilationPassResult(
        pass_id=plan.pass_id,
        evidence_items=[],
        artifacts=[],
        relations=[],
        review_items=[],
        covered_unit_ids=plan.target_unit_ids,
        notes=["Follow-up pass completed."],
    )
