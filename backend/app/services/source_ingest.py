from dataclasses import dataclass

from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import compiler_pass_run_id, compiler_run_id, ingest_job_id
from backend.app.domain.compiler import (
    CompilationBundle,
    CompilationPassPlan,
    CoverageReport,
    SourceManifest,
)
from backend.app.domain.extraction import IngestExtractionResult
from backend.app.domain.graph import GraphBuildCommand, GraphBuildResult
from backend.app.domain.models import SourceRef, WikiPage
from backend.app.repositories.compiler import SQLiteCompilerRepository
from backend.app.repositories.extractions import SQLiteExtractionRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.artifact_projector import ArtifactProjector
from backend.app.services.compilation_merger import CompilationMerger
from backend.app.services.compilation_validator import CompilationValidator
from backend.app.services.compiler_contracts import CompilerLLMClient
from backend.app.services.coverage_gate import CoverageGate
from backend.app.services.graph_builder import GraphBuilder
from backend.app.services.source_page_writer import SourcePageWriter
from backend.app.services.wiki_log import WikiLogWriter


@dataclass(frozen=True)
class SourceIngestResult:
    source: SourceRef
    extraction: IngestExtractionResult
    page: WikiPage
    compiler_run_id: str
    manifest: SourceManifest
    compilation: CompilationBundle
    coverage: CoverageReport
    graph: GraphBuildResult
    pass_count: int


class SourceIngestService:
    def __init__(
        self,
        source_repository: SQLiteSourceRepository,
        compiler_repository: SQLiteCompilerRepository,
        extraction_repository: SQLiteExtractionRepository,
        job_repository: SQLiteIngestJobRepository,
        llm_client: CompilerLLMClient,
        graph_builder: GraphBuilder,
        source_page_writer: SourcePageWriter,
        wiki_log_writer: WikiLogWriter,
        max_file_bytes: int,
        model: str,
        compiler_version: str,
        prompt_version: str,
        schema_version: str,
        max_passes: int = 8,
        max_pass_retries: int = 2,
        max_audit_iterations: int = 2,
        merger: CompilationMerger | None = None,
        validator: CompilationValidator | None = None,
        projector: ArtifactProjector | None = None,
        coverage_gate: CoverageGate | None = None,
    ) -> None:
        self.source_repository = source_repository
        self.compiler_repository = compiler_repository
        self.extraction_repository = extraction_repository
        self.job_repository = job_repository
        self.llm_client = llm_client
        self.graph_builder = graph_builder
        self.source_page_writer = source_page_writer
        self.wiki_log_writer = wiki_log_writer
        self.max_file_bytes = max_file_bytes
        self.model = model
        self.compiler_version = compiler_version
        self.prompt_version = prompt_version
        self.schema_version = schema_version
        self.max_passes = max_passes
        self.max_pass_retries = max_pass_retries
        self.max_audit_iterations = max_audit_iterations
        self.merger = merger or CompilationMerger()
        self.validator = validator or CompilationValidator()
        self.projector = projector or ArtifactProjector()
        self.coverage_gate = coverage_gate or CoverageGate()

    async def ingest(self, source_id: str) -> SourceIngestResult:
        source = self.source_repository.get(source_id)
        if source is None:
            raise ValueError(f"Source not found: {source_id}")
        if source.size_bytes is not None and source.size_bytes > self.max_file_bytes:
            raise ValueError(
                f"Source file is too large for direct multimodal ingest: "
                f"{source.size_bytes} bytes > {self.max_file_bytes} bytes"
            )

        job_id = ingest_job_id()
        run_id = compiler_run_id()
        started_at = utc_now_iso()
        self.job_repository.create_ingest_job(job_id, source.id, started_at)
        self.compiler_repository.create_run(
            run_id=run_id,
            source=source,
            compiler_version=self.compiler_version,
            prompt_version=self.prompt_version,
            schema_version=self.schema_version,
            model=self.model,
            started_at=started_at,
        )
        try:
            manifest = await self.llm_client.profile_source(source)
            self.compiler_repository.save_manifest(
                run_id,
                source.id,
                manifest,
                utc_now_iso(),
            )
            self.compiler_repository.update_stage(
                run_id,
                source.id,
                "compiling",
                utc_now_iso(),
            )
            compilation = self.merger.empty()
            executed_passes = 0
            for plan in manifest.compilation_plan:
                if executed_passes >= self.max_passes:
                    break
                compilation = await self._execute_pass(
                    source,
                    run_id,
                    manifest,
                    plan,
                    compilation,
                    iteration=0,
                )
                executed_passes += 1
            if executed_passes == 0:
                raise ValueError("Source manifest did not provide a compilation plan.")

            compilation, coverage, executed_passes = await self._audit_and_fill_gaps(
                source,
                run_id,
                manifest,
                compilation,
                executed_passes,
            )
            self.validator.validate(manifest, compilation)

            self.compiler_repository.update_stage(
                run_id,
                source.id,
                "integrating",
                utc_now_iso(),
            )
            extraction = self.projector.project(source, manifest, compilation)
            page = self.source_page_writer.write(
                source,
                extraction,
                compilation=compilation,
            )
            self.extraction_repository.save(source, extraction, page)
            self.compiler_repository.save_artifacts(
                run_id,
                source,
                compilation,
                utc_now_iso(),
            )
            self.compiler_repository.update_stage(
                run_id,
                source.id,
                "graphing",
                utc_now_iso(),
            )
            graph = await self.graph_builder.build(
                GraphBuildCommand(source_ids=[source.id], rebuild=True)
            )
            finished_at = utc_now_iso()
            final_status = (
                "ingested" if coverage.coverage_status == "complete" else "needs_review"
            )
            self.compiler_repository.finish_run(
                run_id,
                source.id,
                final_status,
                coverage.coverage_status,
                finished_at,
            )
            self.job_repository.mark_completed(job_id, finished_at)
            self.wiki_log_writer.append_source_ingested(
                finished_at,
                source.id,
                extraction.source_title or source.title,
                page.path,
            )
            self.wiki_log_writer.append_compiler_completed(
                timestamp=finished_at,
                compiler_run_id=run_id,
                source_id=source.id,
                pass_count=executed_passes,
                artifact_count=len(compilation.artifacts),
                coverage_status=coverage.coverage_status,
                graph_run_id=graph.graph_run_id,
            )
            updated_source = self.source_repository.get(source.id) or source
            return SourceIngestResult(
                source=updated_source,
                extraction=extraction,
                page=page,
                compiler_run_id=run_id,
                manifest=manifest,
                compilation=compilation,
                coverage=coverage,
                graph=graph,
                pass_count=executed_passes,
            )
        except Exception as exc:
            failed_at = utc_now_iso()
            self.compiler_repository.fail_run(run_id, source.id, str(exc), failed_at)
            self.job_repository.mark_failed(job_id, failed_at, str(exc))
            raise

    async def _execute_pass(
        self,
        source: SourceRef,
        run_id: str,
        manifest: SourceManifest,
        plan: CompilationPassPlan,
        compilation: CompilationBundle,
        iteration: int,
    ) -> CompilationBundle:
        current_plan = plan
        last_error: Exception | None = None
        for attempt in range(self.max_pass_retries + 1):
            pass_run_id = compiler_pass_run_id()
            persisted_plan = (
                current_plan
                if attempt == 0
                else current_plan.model_copy(
                    update={"pass_id": f"{plan.pass_id}__retry_{attempt}"}
                )
            )
            self.compiler_repository.start_pass(
                pass_run_id,
                run_id,
                persisted_plan,
                iteration,
                utc_now_iso(),
            )
            try:
                result = await self.llm_client.compile_source_pass(
                    source,
                    manifest,
                    current_plan,
                    compilation,
                )
                merged = self.merger.merge(compilation, result)
                self.validator.validate(manifest, merged)
                self.compiler_repository.finish_pass(
                    pass_run_id,
                    result,
                    utc_now_iso(),
                )
                return merged
            except Exception as exc:
                last_error = exc
                self.compiler_repository.fail_pass(
                    pass_run_id,
                    str(exc),
                    utc_now_iso(),
                )
                current_plan = plan.model_copy(
                    update={
                        "objective": (
                            f"{plan.objective}\n\nLần trước không đạt validation gate: "
                            f"{exc}. Hãy sửa toàn bộ lỗi provenance/reference này; mọi "
                            "artifact và statement phải có evidence_local_ids hợp lệ."
                        )
                    }
                )
        if last_error is None:
            raise RuntimeError("Compilation pass failed without an error.")
        raise last_error

    async def _audit_and_fill_gaps(
        self,
        source: SourceRef,
        run_id: str,
        manifest: SourceManifest,
        compilation: CompilationBundle,
        executed_passes: int,
    ) -> tuple[CompilationBundle, CoverageReport, int]:
        self.compiler_repository.update_stage(
            run_id,
            source.id,
            "auditing",
            utc_now_iso(),
        )
        report = await self.llm_client.audit_compilation(
            source,
            manifest,
            compilation,
            iteration=0,
        )
        self.coverage_gate.validate_report(manifest, report)
        self.compiler_repository.save_coverage(
            run_id,
            source.id,
            0,
            report,
            utc_now_iso(),
        )
        for iteration in range(1, self.max_audit_iterations):
            if report.coverage_status == "complete" or not report.missing_or_weak_areas:
                break
            for gap in report.missing_or_weak_areas:
                if executed_passes >= self.max_passes:
                    break
                compilation = await self._execute_pass(
                    source,
                    run_id,
                    manifest,
                    gap.recommended_pass.as_plan(),
                    compilation,
                    iteration,
                )
                executed_passes += 1
            report = await self.llm_client.audit_compilation(
                source,
                manifest,
                compilation,
                iteration=iteration,
            )
            self.coverage_gate.validate_report(manifest, report)
            self.compiler_repository.save_coverage(
                run_id,
                source.id,
                iteration,
                report,
                utc_now_iso(),
            )
        return compilation, report, executed_passes
