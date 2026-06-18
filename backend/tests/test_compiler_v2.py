import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app.application.container import AppContainer, get_container
from backend.app.core.config import Settings
from backend.app.db.connection import SQLiteDatabase
from backend.app.db.migrations import MigrationRunner
from backend.app.domain.compiler import (
    CompilationBundle,
    CompiledArtifact,
    CoverageGap,
    CoverageReport,
    CoverageUnitAssessment,
    RecommendedCompilationPass,
)
from backend.app.main import create_app
from backend.app.repositories.compiler import SQLiteCompilerRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.compilation_validator import (
    CompilationValidationError,
    CompilationValidator,
)
from backend.app.services.coverage_gate import CoverageGate, CoverageGateError
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter
from backend.tests.compiler_fixtures import FakeCompilerClient, build_test_ingest_service


def test_coverage_gap_triggers_follow_up_pass_and_second_audit(tmp_path) -> None:
    asyncio.run(_run_coverage_follow_up_test(tmp_path))


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
        missing_or_weak_areas=[
            CoverageGap(
                description="The caveat needs another pass.",
                likely_unit_ids=["unit_caveat"],
                severity="high",
                recommended_pass=RecommendedCompilationPass(
                    pass_id="pass_caveat_follow_up",
                    objective="Verify the persistence caveat.",
                    target_unit_ids=["unit_caveat"],
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
    assert llm.compilation_calls == ["pass_core", "pass_caveat_follow_up"]
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
    app = create_app()
    app.dependency_overrides[get_container] = lambda: AppContainer(
        settings=Settings(
            database_path=database.database_path,
            raw_dir=tmp_path / "raw",
            wiki_dir=wiki_dir,
        ),
        database=database,
    )
    response = TestClient(app).get(f"/api/sources/{source.id}/compilation")
    assert response.status_code == 200
    assert response.json()["compiler_run_id"] == result.compiler_run_id


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
                related_artifact_local_ids=[],
                statements=[],
                confidence=0.5,
                status="active",
                review_status="needs_review",
                metadata=[],
            )
        ],
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

    assert first[-1].name == "knowledge_compiler_v2"
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
        missing_or_weak_areas=[],
        provenance_issues=[],
        overgeneralization_risks=[],
        confidence=0.8,
    )

    with pytest.raises(CoverageGateError, match="units remain incomplete"):
        CoverageGate().validate_report(manifest, report)


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
