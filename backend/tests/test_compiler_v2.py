import asyncio
import sqlite3
from zipfile import ZipFile

import pytest

from backend.app.api.routes import sources as sources_route
from backend.app.db.connection import SQLiteDatabase
from backend.app.db.migrations import MigrationRunner
from backend.app.domain.compiler import (
    ArtifactStatement,
    CompilationBundle,
    CompilationPassPlan,
    CompilationPassResult,
    CompiledArtifact,
    CompiledDetailCoverage,
    CompiledEvidence,
    CoverageDetailAssessment,
    CoverageGap,
    CoverageReport,
    CoverageUnitAssessment,
    ObservedDetail,
    RecommendedCompilationPass,
    SourceLocator,
    StatementReference,
)
from backend.app.repositories.compiler import SQLiteCompilerRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.artifact_projector import ArtifactProjector
from backend.app.services.compilation_merger import CompilationMerger
from backend.app.services.compilation_validator import (
    CompilationValidationError,
    CompilationValidator,
)
from backend.app.services.coverage_gate import CoverageGate
from backend.app.services.manifest_planner import ManifestPlanner
from backend.app.services.source_ingest import SourceIngestService
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.source_text import extract_source_text_context
from backend.app.services.wiki_log import WikiLogWriter
from backend.tests.compiler_fixtures import FakeCompilerClient, build_test_ingest_service


def test_coverage_gap_triggers_follow_up_pass_and_second_audit(tmp_path) -> None:
    asyncio.run(_run_coverage_follow_up_test(tmp_path))


def test_odt_source_text_context_preserves_paragraphs(tmp_path) -> None:
    source_path = tmp_path / "source.odt"
    content_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <office:document-content
      xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
      xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
      <office:body>
        <office:text>
          <text:p>Thanh toán trước hạn</text:p>
          <text:p>Người sở hữu được hưởng lãi suất thanh toán trước hạn theo thỏa thuận.</text:p>
        </office:text>
      </office:body>
    </office:document-content>
    """
    with ZipFile(source_path, "w") as archive:
        archive.writestr("content.xml", content_xml)

    context = extract_source_text_context(source_path, "odt", max_chars=10_000)

    assert context is not None
    assert context.truncated is False
    assert "P0001: Thanh toán trước hạn" in context.text
    assert (
        "P0002: Người sở hữu được hưởng lãi suất thanh toán trước hạn theo thỏa thuận."
        in context.text
    )


async def _run_coverage_follow_up_test(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "app.sqlite")
    wiki_dir = tmp_path / "wiki"
    MigrationRunner(database).run()
    source_path = tmp_path / "source.md"
    source_path.write_text("# Source\n\nPersistent wiki and RAG comparison.\n")
    source = SourceRegistryService(
        source_repository=SQLiteSourceRepository(database),
        job_repository=SQLiteIngestJobRepository(database),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    ).register(
        RegisterSourceCommand(
            path=source_path,
            title="Compiler Source",
            source_type="markdown",
        )
    )
    incomplete = CoverageReport(
        coverage_status="incomplete",
        covered_unit_ids=["unit_wiki", "unit_rag"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit_id,
                status="incomplete" if unit_id == "unit_caveat" else "complete",
                represented_knowledge=["Core knowledge represented."],
                missing_knowledge=(
                    ["Persistence caveat missing."] if unit_id == "unit_caveat" else []
                ),
                confidence=0.8,
            )
            for unit_id in ["unit_wiki", "unit_rag", "unit_caveat"]
        ],
        detail_assessments=[
            *_complete_detail_assessments(["detail_wiki", "detail_rag"]),
            _detail_assessment("detail_caveat", "unit_caveat", status="missing"),
        ],
        missing_or_weak_areas=[
            CoverageGap(
                description="The caveat needs another pass.",
                likely_unit_ids=["unit_caveat"],
                likely_detail_ids=["detail_caveat"],
                severity="high",
                recommended_pass=RecommendedCompilationPass(
                    pass_id="pass_caveat_follow_up",
                    objective="Verify the persistence caveat.",
                    target_unit_ids=["unit_caveat"],
                    target_detail_ids=["detail_caveat"],
                    expected_outputs=["qualified artifact"],
                ),
            )
        ],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.8,
    )
    complete = CoverageReport(
        coverage_status="complete",
        covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit_id,
                status="complete",
                represented_knowledge=["Core knowledge represented."],
                missing_knowledge=[],
                confidence=0.95,
            )
            for unit_id in ["unit_wiki", "unit_rag", "unit_caveat"]
        ],
        detail_assessments=_complete_detail_assessments(),
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.95,
    )
    llm = FakeCompilerClient([incomplete, complete])

    result = await build_test_ingest_service(
        database,
        wiki_dir,
        compiler_client=llm,
    ).ingest(source.id)

    assert result.source.status == "ingested"
    assert result.pass_count == 2
    assert llm.compilation_calls == [
        "pass_core",
        "selective_repair_1",
    ]
    assert llm.audit_calls == 2
    with sqlite3.connect(database.database_path) as connection:
        pass_count = connection.execute("SELECT COUNT(*) FROM compiler_passes").fetchone()[0]
        coverage_count = connection.execute(
            "SELECT COUNT(*) FROM coverage_reports"
        ).fetchone()[0]
    assert pass_count == 2
    assert coverage_count == 2
    inspection = SQLiteCompilerRepository(database).get_latest_inspection(source.id)
    assert inspection is not None
    assert inspection.pass_count == 2
    assert inspection.coverage_status == "complete"
    assert len(inspection.artifacts) == 2
    response = sources_route.inspect_compilation(source.id, container=type(
        "Container",
        (),
        {"database": database},
    )())
    assert response.compiler_run_id == result.compiler_run_id


def test_invalid_compilation_pass_is_retried_with_clean_state(tmp_path) -> None:
    asyncio.run(_run_pass_retry_test(tmp_path))


async def _run_pass_retry_test(tmp_path) -> None:
    class InvalidThenValidCompiler(FakeCompilerClient):
        attempts = 0

        async def compile_source_pass(self, source, manifest, plan, existing):
            result = await super().compile_source_pass(source, manifest, plan, existing)
            self.attempts += 1
            if self.attempts == 1:
                invalid_artifact = result.artifacts[0].model_copy(
                    update={"evidence_local_ids": []}
                )
                return result.model_copy(
                    update={"artifacts": [invalid_artifact, *result.artifacts[1:]]}
                )
            return result

    database = SQLiteDatabase(tmp_path / "app.sqlite")
    wiki_dir = tmp_path / "wiki"
    MigrationRunner(database).run()
    source_path = tmp_path / "source.md"
    source_path.write_text("# Source\n\nKnowledge compiler.\n")
    source = SourceRegistryService(
        source_repository=SQLiteSourceRepository(database),
        job_repository=SQLiteIngestJobRepository(database),
        wiki_log_writer=WikiLogWriter(wiki_dir),
    ).register(
        RegisterSourceCommand(
            path=source_path,
            title="Retry Source",
            source_type="markdown",
        )
    )
    compiler = InvalidThenValidCompiler()

    result = await build_test_ingest_service(
        database,
        wiki_dir,
        compiler_client=compiler,
    ).ingest(source.id)

    assert result.source.status == "ingested"
    assert compiler.attempts == 2
    with sqlite3.connect(database.database_path) as connection:
        statuses = connection.execute(
            "SELECT status FROM compiler_passes ORDER BY started_at, id"
        ).fetchall()
    assert sorted(status[0] for status in statuses) == ["completed", "failed"]


def test_compilation_validator_rejects_dangling_evidence_reference() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    bundle = CompilationBundle(
        evidence_items=[],
        artifacts=[
            CompiledArtifact(
                local_id="art_invalid",
                artifact_type="concept",
                title="Invalid",
                summary="Invalid provenance.",
                content="Missing evidence.",
                aliases=[],
                scope=[],
                evidence_local_ids=["ev_missing"],
                source_unit_ids=["unit_wiki"],
                related_artifact_local_ids=[],
                statements=[],
                confidence=0.5,
                status="active",
                review_status="unreviewed",
                metadata=[],
            )
        ],
        semantic_nodes=[],
        relations=[],
        review_items=[],
        covered_unit_ids=[],
        notes=[],
    )

    with pytest.raises(CompilationValidationError, match="unknown IDs"):
        CompilationValidator().validate(manifest, bundle)


def test_compiler_migration_is_idempotent(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "app.sqlite")

    first = MigrationRunner(database).run()
    second = MigrationRunner(database).run()

    assert first[-1].name == "semantic_artifact_retrieval"
    assert second == []


def test_coverage_gate_rejects_false_complete_report() -> None:
    compiler = FakeCompilerClient()
    manifest = asyncio.run(compiler.profile_source(_source()))
    report = CoverageReport(
        coverage_status="complete",
        covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit.local_id,
                status="incomplete" if unit.local_id == "unit_caveat" else "complete",
                represented_knowledge=[],
                missing_knowledge=(
                    ["Missing caveat."] if unit.local_id == "unit_caveat" else []
                ),
                confidence=0.8,
            )
            for unit in manifest.content_units
        ],
        detail_assessments=[
            _detail_assessment(
                "detail_wiki",
                "unit_wiki",
                status="covered",
            ),
            _detail_assessment(
                "detail_rag",
                "unit_rag",
                status="covered",
            ),
            _detail_assessment(
                "detail_caveat",
                "unit_caveat",
                status="missing",
            ),
        ],
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.8,
    )

    bundle = asyncio.run(_compiled_bundle())
    reconciled = CoverageGate().validate_report(
        manifest,
        report,
        compilation=bundle,
    )
    assert reconciled.coverage_status == "incomplete"
    assert reconciled.unit_assessments[-1].status == "incomplete"


def test_coverage_gate_rejects_false_detail_complete_report() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    full_result = asyncio.run(
        compiler.compile_source_pass(
            source,
            manifest,
            manifest.compilation_plan[0],
            CompilationMerger.empty(),
        )
    )
    missing_detail_result = full_result.model_copy(
        update={
            "detail_coverage": [
                detail
                for detail in full_result.detail_coverage
                if detail.detail_id != "detail_caveat"
            ]
        }
    )
    compilation = CompilationMerger().merge(
        CompilationMerger.empty(),
        missing_detail_result,
    )
    false_complete = CoverageReport(
        coverage_status="complete",
        covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit.local_id,
                status="complete",
                represented_knowledge=[unit.summary],
                missing_knowledge=[],
                confidence=0.9,
            )
            for unit in manifest.content_units
        ],
        detail_assessments=_complete_detail_assessments(),
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.9,
    )

    reconciled = CoverageGate().reconcile(
        manifest,
        compilation,
        false_complete,
        iteration=0,
    )

    assert reconciled.coverage_status == "incomplete"
    detail_assessments = {
        item.detail_id: item for item in reconciled.detail_assessments
    }
    assert detail_assessments["detail_caveat"].status == "missing"
    assert any(
        "detail_caveat" in gap.likely_detail_ids
        for gap in reconciled.missing_or_weak_areas
    )


def test_coverage_gate_repairs_detail_covered_with_wrong_source_unit_refs() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    full_result = asyncio.run(
        compiler.compile_source_pass(
            source,
            manifest,
            manifest.compilation_plan[0],
            CompilationMerger.empty(),
        )
    )
    wrong_detail_coverage = [
        detail.model_copy(
            update={
                "evidence_local_ids": ["ev_wiki"],
                "artifact_local_ids": ["art_wiki"],
                "statement_refs": [
                    StatementReference(
                        artifact_local_id="art_wiki",
                        statement_local_id="stmt_wiki_persists",
                    )
                ],
            }
        )
        if detail.detail_id == "detail_caveat"
        else detail
        for detail in full_result.detail_coverage
    ]
    wrong_result = full_result.model_copy(
        update={"detail_coverage": wrong_detail_coverage}
    )
    compilation = CompilationMerger().merge(CompilationMerger.empty(), wrong_result)

    CompilationValidator().validate(manifest, compilation)
    assert "detail_caveat" not in CompilationValidator.supported_detail_ids(
        compilation,
        manifest,
    )

    false_complete = CoverageReport(
        coverage_status="complete",
        covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit.local_id,
                status="complete",
                represented_knowledge=[unit.summary],
                missing_knowledge=[],
                confidence=0.9,
            )
            for unit in manifest.content_units
        ],
        detail_assessments=_complete_detail_assessments(),
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.9,
    )

    reconciled = CoverageGate().reconcile(
        manifest,
        compilation,
        false_complete,
        iteration=0,
    )

    detail_assessments = {
        item.detail_id: item for item in reconciled.detail_assessments
    }
    assert reconciled.coverage_status == "incomplete"
    assert detail_assessments["detail_caveat"].status == "missing"
    assert any(
        "detail_caveat" in gap.likely_detail_ids
        for gap in reconciled.missing_or_weak_areas
    )


def test_coverage_gate_converts_missing_audit_assessments_to_repair_gaps() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    compilation = asyncio.run(_compiled_bundle())
    incomplete_audit = CoverageReport(
        coverage_status="complete",
        covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit_id,
                status="complete",
                represented_knowledge=["Auditor represented this unit."],
                missing_knowledge=[],
                confidence=0.9,
            )
            for unit_id in ["unit_wiki", "unit_rag"]
        ],
        detail_assessments=_complete_detail_assessments(
            ["detail_wiki", "detail_rag"]
        ),
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.9,
    )

    reconciled = CoverageGate().reconcile(
        manifest,
        compilation,
        incomplete_audit,
        iteration=0,
    )

    assert reconciled.coverage_status == "incomplete"
    unit_assessments = {item.unit_id: item for item in reconciled.unit_assessments}
    assert unit_assessments["unit_caveat"].status == "incomplete"
    detail_assessments = {
        item.detail_id: item for item in reconciled.detail_assessments
    }
    assert detail_assessments["detail_caveat"].status == "missing"
    assert any(
        "unit_caveat" in gap.likely_unit_ids
        for gap in reconciled.missing_or_weak_areas
    )
    assert any(
        "detail_caveat" in gap.likely_detail_ids
        for gap in reconciled.missing_or_weak_areas
    )


def test_compiler_can_cover_details_discovered_beyond_manifest() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    base = asyncio.run(_compiled_bundle())
    discovered_detail = ObservedDetail(
        local_id="detail_caveat_extra",
        source_unit_id="unit_caveat",
        detail_kind="qualification",
        description="A source-specific qualification omitted by the manifest.",
        locator=manifest.content_units[2].locator,
        importance=0.82,
        query_hint="qualification omitted by manifest",
    )
    evidence = CompiledEvidence(
        local_id="ev_caveat_extra",
        source_unit_ids=["unit_caveat"],
        locator=manifest.content_units[2].locator,
        modality="text",
        content=(
            "The source states the caveat with a condition, scope, and consequence "
            "that were omitted by the manifest summary."
        ),
        summary="Source-close evidence for the discovered qualification.",
        confidence=0.9,
    )
    artifact = CompiledArtifact(
        local_id="art_caveat_extra",
        artifact_type="qualification",
        title="Discovered Caveat Qualification",
        summary="A qualification discovered during deep compilation.",
        content="A source-specific caveat includes condition, scope, and consequence.",
        aliases=[],
        scope=[],
        evidence_local_ids=["ev_caveat_extra"],
        source_unit_ids=["unit_caveat"],
        related_artifact_local_ids=["art_wiki"],
        statements=[
            ArtifactStatement(
                local_id="stmt_caveat_extra",
                statement_type="qualification",
                text=(
                    "The caveat includes a condition, scope, and consequence omitted "
                    "by the manifest summary."
                ),
                subject="Caveat",
                predicate="includes",
                object="condition, scope, and consequence",
                object_type="qualification",
                evidence_local_ids=["ev_caveat_extra"],
                source_unit_ids=["unit_caveat"],
                qualifiers=[],
                confidence=0.88,
                status="active",
            )
        ],
        confidence=0.88,
        status="active",
        review_status="unreviewed",
        metadata=[],
    )
    incoming = CompilationPassResult(
        pass_id="deep_compile_extra",
        discovered_details=[discovered_detail],
        evidence_items=[evidence],
        artifacts=[artifact],
        semantic_nodes=[],
        relations=[],
        detail_coverage=[
            CompiledDetailCoverage(
                detail_id="detail_caveat_extra",
                status="covered",
                evidence_local_ids=["ev_caveat_extra"],
                artifact_local_ids=["art_caveat_extra"],
                statement_refs=[
                    StatementReference(
                        artifact_local_id="art_caveat_extra",
                        statement_local_id="stmt_caveat_extra",
                    )
                ],
                notes="Deep compile represented a detail omitted by the manifest.",
                confidence=0.88,
            )
        ],
        review_items=[],
        covered_unit_ids=["unit_caveat"],
        notes=[],
    )
    compilation = CompilationMerger().merge(base, incoming)

    CompilationValidator().validate(manifest, compilation)
    assert "detail_caveat_extra" in CompilationValidator.supported_detail_ids(
        compilation
    )

    complete_audit = CoverageReport(
        coverage_status="complete",
        covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit.local_id,
                status="complete",
                represented_knowledge=[unit.summary],
                missing_knowledge=[],
                confidence=0.9,
            )
            for unit in manifest.content_units
        ],
        detail_assessments=[
            *_complete_detail_assessments(),
            CoverageDetailAssessment(
                detail_id="detail_caveat_extra",
                unit_id="unit_caveat",
                status="covered",
                represented_knowledge=["The discovered qualification is represented."],
                missing_knowledge=[],
                evidence_local_ids=["ev_caveat_extra"],
                artifact_local_ids=["art_caveat_extra"],
                statement_refs=[
                    StatementReference(
                        artifact_local_id="art_caveat_extra",
                        statement_local_id="stmt_caveat_extra",
                    )
                ],
                confidence=0.9,
            ),
        ],
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.9,
    )

    reconciled = CoverageGate().reconcile(
        manifest,
        compilation,
        complete_audit,
        iteration=0,
    )

    assert reconciled.coverage_status == "complete"
    assert any(
        item.detail_id == "detail_caveat_extra"
        for item in reconciled.detail_assessments
    )


async def _compiled_bundle() -> CompilationBundle:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = await compiler.profile_source(source)
    result = await compiler.compile_source_pass(
        source,
        manifest,
        manifest.compilation_plan[0],
        CompilationBundle(
            evidence_items=[],
            artifacts=[],
            semantic_nodes=[],
            relations=[],
            review_items=[],
            covered_unit_ids=[],
            notes=[],
        ),
    )
    return CompilationMerger().merge(CompilationMerger.empty(), result)


def test_manifest_planner_adds_pass_for_unplanned_units() -> None:
    compiler = FakeCompilerClient()
    manifest = asyncio.run(compiler.profile_source(_source()))
    incomplete = manifest.model_copy(
        update={
            "compilation_plan": [
                CompilationPassPlan(
                    pass_id="only_wiki",
                    objective="Compile one unit.",
                    target_unit_ids=["unit_wiki"],
                    expected_outputs=["artifact"],
                )
            ]
        }
    )

    normalized = ManifestPlanner().ensure_complete_plan(incomplete, max_passes=2)

    planned = {
        unit_id
        for plan in normalized.compilation_plan
        for unit_id in plan.target_unit_ids
    }
    assert planned == {"unit_wiki", "unit_rag", "unit_caveat"}
    assert len(normalized.compilation_plan) == 2


def test_pass_validation_rejects_target_unit_without_grounded_statement() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    evidence = CompiledEvidence(
        local_id="ev_only",
        source_unit_ids=["unit_wiki"],
        locator=manifest.content_units[0].locator,
        modality="text",
        content="Only wiki is represented.",
        summary="Partial evidence.",
        confidence=0.9,
    )
    artifact = CompiledArtifact(
        local_id="art_only",
        artifact_type="concept",
        title="Only Wiki",
        summary="Partial artifact.",
        content="Only one source unit is compiled.",
        aliases=[],
        scope=[],
        evidence_local_ids=["ev_only"],
        source_unit_ids=["unit_wiki"],
        related_artifact_local_ids=[],
        statements=[
            ArtifactStatement(
                local_id="stmt_only",
                statement_type="fact",
                text="Only wiki is represented.",
                subject="Wiki",
                predicate="is",
                object="represented",
                object_type="text",
                evidence_local_ids=["ev_only"],
                source_unit_ids=["unit_wiki"],
                qualifiers=[],
                confidence=0.9,
                status="active",
            )
        ],
        confidence=0.9,
        status="active",
        review_status="unreviewed",
        metadata=[],
    )
    result = CompilationPassResult(
        pass_id="partial",
        evidence_items=[evidence],
        artifacts=[artifact],
        semantic_nodes=[],
        relations=[],
        review_items=[],
        covered_unit_ids=["unit_wiki", "unit_rag"],
        notes=[],
    )
    merged = CompilationMerger().merge(CompilationMerger.empty(), result)
    plan = CompilationPassPlan(
        pass_id="partial",
        objective="Compile wiki and RAG.",
        target_unit_ids=["unit_wiki", "unit_rag"],
        expected_outputs=["artifacts"],
    )

    with pytest.raises(CompilationValidationError, match="unit_rag"):
        CompilationValidator().validate_pass(manifest, plan, result, merged)


def test_coverage_gate_repairs_inconsistent_incomplete_report() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    full_result = asyncio.run(
        compiler.compile_source_pass(
            source,
            manifest,
            manifest.compilation_plan[0],
            CompilationMerger.empty(),
        )
    )
    wiki_artifact = full_result.artifacts[0].model_copy(
        update={
            "evidence_local_ids": ["ev_wiki"],
            "source_unit_ids": ["unit_wiki"],
            "statements": [full_result.artifacts[0].statements[0]],
        }
    )
    partial_result = full_result.model_copy(
        update={
            "evidence_items": [full_result.evidence_items[0]],
            "artifacts": [wiki_artifact],
            "semantic_nodes": [full_result.semantic_nodes[0]],
            "relations": [],
            "detail_coverage": [
                detail
                for detail in full_result.detail_coverage
                if detail.detail_id == "detail_wiki"
            ],
            "covered_unit_ids": ["unit_wiki"],
        }
    )
    partial = CompilationMerger().merge(CompilationMerger.empty(), partial_result)
    inconsistent = CoverageReport(
        coverage_status="incomplete",
        covered_unit_ids=["unit_wiki"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit.local_id,
                status="complete",
                represented_knowledge=[unit.summary],
                missing_knowledge=[],
                confidence=0.9,
            )
            for unit in manifest.content_units
        ],
        detail_assessments=_complete_detail_assessments(),
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.9,
    )

    reconciled = CoverageGate().reconcile(
        manifest,
        partial,
        inconsistent,
        iteration=0,
    )

    assert reconciled.covered_unit_ids == ["unit_wiki"]
    assert reconciled.coverage_status == "incomplete"
    assert {gap.likely_unit_ids[0] for gap in reconciled.missing_or_weak_areas} == {
        "unit_rag",
        "unit_caveat",
    }
    assessments = {item.unit_id: item for item in reconciled.unit_assessments}
    assert assessments["unit_rag"].status == "incomplete"
    assert assessments["unit_rag"].missing_knowledge


def test_coverage_gate_repairs_uncovered_ledger_detail() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    full_result = asyncio.run(
        compiler.compile_source_pass(
            source,
            manifest,
            manifest.compilation_plan[0],
            CompilationMerger.empty(),
        )
    )
    compilation = CompilationMerger().merge(CompilationMerger.empty(), full_result)
    extra_detail = ObservedDetail(
        local_id="ledger_extra_obligation",
        source_unit_id="unit_caveat",
        detail_kind="source_obligation",
        description="A source obligation that has not been compiled yet.",
        locator=manifest.content_units[2].locator,
        importance=0.9,
        query_hint="uncompiled source obligation",
    )
    compilation = compilation.model_copy(
        update={"ledger_items": [*compilation.ledger_items, extra_detail]}
    )
    false_complete = CoverageReport(
        coverage_status="complete",
        covered_unit_ids=["unit_wiki", "unit_rag", "unit_caveat"],
        unit_assessments=[
            CoverageUnitAssessment(
                unit_id=unit.local_id,
                status="complete",
                represented_knowledge=[unit.summary],
                missing_knowledge=[],
                confidence=0.9,
            )
            for unit in manifest.content_units
        ],
        detail_assessments=_complete_detail_assessments(),
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.9,
    )

    reconciled = CoverageGate().reconcile(
        manifest,
        compilation,
        false_complete,
        iteration=0,
    )

    assert reconciled.coverage_status == "incomplete"
    assert any(
        "ledger_extra_obligation" in gap.recommended_pass.target_detail_ids
        for gap in reconciled.missing_or_weak_areas
    )


def test_audit_additional_details_are_promoted_to_ledger() -> None:
    detail = ObservedDetail(
        local_id="audit_found_detail",
        source_unit_id="unit_caveat",
        detail_kind="audit_gap",
        description="Auditor found a source detail omitted by the pass ledger.",
        locator=SourceLocator(kind="section", value="caveat", metadata=[]),
        importance=0.9,
        query_hint="auditor found source detail",
    )
    report = CoverageReport(
        additional_details=[detail],
        coverage_status="incomplete",
        covered_unit_ids=[],
        unit_assessments=[],
        detail_assessments=[],
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.5,
    )

    compilation = CompilationMerger.empty()
    updated = SourceIngestService._promote_audit_details(
        compilation,
        report,
    )

    assert [item.local_id for item in updated.ledger_items] == ["audit_found_detail"]


def test_pass_result_normalization_marks_unmapped_ledger_details_missing() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    plan = manifest.compilation_plan[0]
    result = asyncio.run(
        compiler.compile_source_pass(
            source,
            manifest,
            plan,
            CompilationMerger.empty(),
        )
    ).model_copy(update={"detail_coverage": []})

    normalized = SourceIngestService._normalize_pass_result(
        manifest,
        plan,
        CompilationMerger.empty(),
        result,
    )
    merged = CompilationMerger().merge(CompilationMerger.empty(), normalized)

    CompilationValidator().validate_pass(
        manifest,
        plan,
        normalized,
        merged,
        require_target_coverage=False,
    )
    coverage_by_detail = {
        item.detail_id: item
        for item in normalized.detail_coverage
    }
    assert set(coverage_by_detail) == {
        "detail_wiki",
        "detail_rag",
        "detail_caveat",
    }
    assert all(item.status == "missing" for item in coverage_by_detail.values())


def test_pass_result_normalization_carries_target_details_into_ledger() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    plan = manifest.compilation_plan[0]
    result = asyncio.run(
        compiler.compile_source_pass(
            source,
            manifest,
            plan,
            CompilationMerger.empty(),
        )
    ).model_copy(update={"ledger_items": [], "detail_coverage": []})

    normalized = SourceIngestService._normalize_pass_result(
        manifest,
        plan,
        CompilationMerger.empty(),
        result,
    )
    merged = CompilationMerger().merge(CompilationMerger.empty(), normalized)

    CompilationValidator().validate_pass(
        manifest,
        plan,
        normalized,
        merged,
        require_target_coverage=False,
    )
    assert {item.local_id for item in normalized.ledger_items} == {
        "detail_wiki",
        "detail_rag",
        "detail_caveat",
    }
    assert {
        item.detail_id
        for item in normalized.detail_coverage
        if item.status == "missing"
    } == {"detail_wiki", "detail_rag", "detail_caveat"}


def test_merger_preserves_existing_statements_when_artifact_is_enriched() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    initial_result = asyncio.run(
        compiler.compile_source_pass(
            source,
            manifest,
            manifest.compilation_plan[0],
            CompilationMerger.empty(),
        )
    )
    initial = CompilationMerger().merge(CompilationMerger.empty(), initial_result)
    artifact = initial_result.artifacts[0]
    enrichment = artifact.model_copy(
        update={
            "content": "Additional grounded detail.",
            "statements": [artifact.statements[1]],
        }
    )
    incoming = initial_result.model_copy(
        update={
            "evidence_items": [],
            "artifacts": [enrichment],
            "semantic_nodes": [],
            "relations": [],
            "covered_unit_ids": ["unit_caveat"],
        }
    )

    merged = CompilationMerger().merge(initial, incoming)
    merged_artifact = next(
        item for item in merged.artifacts if item.local_id == artifact.local_id
    )

    assert len(merged_artifact.statements) == 2
    assert "Additional grounded detail." in merged_artifact.content


def test_artifact_projector_adds_recurring_statement_subject_entity() -> None:
    compiler = FakeCompilerClient()
    source = _source()
    manifest = asyncio.run(compiler.profile_source(source))
    result = asyncio.run(
        compiler.compile_source_pass(
            source,
            manifest,
            manifest.compilation_plan[0],
            CompilationMerger.empty(),
        )
    )
    bundle = CompilationMerger().merge(CompilationMerger.empty(), result)
    bundle = bundle.model_copy(update={"semantic_nodes": []})

    projected = ArtifactProjector().project(source, manifest, bundle)
    entities = {entity.name: entity for entity in projected.entities}

    assert entities["LLM Wiki"].entity_type == "statement_subject"
    assert entities["LLM Wiki"].evidence_local_ids == ["ev_wiki", "ev_caveat"]
    assert "Traditional RAG" not in entities


def _complete_detail_assessments(
    detail_ids: list[str] | None = None,
) -> list[CoverageDetailAssessment]:
    return [
        _detail_assessment(detail_id, _DETAIL_FIXTURES[detail_id]["unit_id"])
        for detail_id in (detail_ids or list(_DETAIL_FIXTURES))
    ]


def _detail_assessment(
    detail_id: str,
    unit_id: str,
    status: str = "covered",
) -> CoverageDetailAssessment:
    fixture = _DETAIL_FIXTURES[detail_id]
    is_covered = status == "covered"
    return CoverageDetailAssessment(
        detail_id=detail_id,
        unit_id=unit_id,
        status=status,
        represented_knowledge=[fixture["represented"]] if is_covered else [],
        missing_knowledge=[] if is_covered else [f"{detail_id} is missing."],
        evidence_local_ids=[fixture["evidence_id"]] if is_covered else [],
        artifact_local_ids=[fixture["artifact_id"]] if is_covered else [],
        statement_refs=[
            StatementReference(
                artifact_local_id=fixture["artifact_id"],
                statement_local_id=fixture["statement_id"],
            )
        ]
        if is_covered
        else [],
        confidence=0.9 if is_covered else 0.6,
    )


_DETAIL_FIXTURES = {
    "detail_wiki": {
        "unit_id": "unit_wiki",
        "evidence_id": "ev_wiki",
        "artifact_id": "art_wiki",
        "statement_id": "stmt_wiki_persists",
        "represented": "LLM Wiki persistence is represented.",
    },
    "detail_rag": {
        "unit_id": "unit_rag",
        "evidence_id": "ev_rag",
        "artifact_id": "art_rag",
        "statement_id": "stmt_rag_retrieves",
        "represented": "RAG retrieval behavior is represented.",
    },
    "detail_caveat": {
        "unit_id": "unit_caveat",
        "evidence_id": "ev_caveat",
        "artifact_id": "art_wiki",
        "statement_id": "stmt_wiki_caveat",
        "represented": "The persistence caveat is represented.",
    },
}


def _source():
    from pathlib import Path

    from backend.app.domain.models import SourceRef

    return SourceRef(
        id="src_test",
        title="Test",
        path=Path("test.md"),
        source_type="markdown",
        sha256="abc",
    )
