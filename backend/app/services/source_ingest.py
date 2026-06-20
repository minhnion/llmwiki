from dataclasses import dataclass
from pathlib import Path

from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import compiler_pass_run_id, compiler_run_id, ingest_job_id
from backend.app.domain.compiler import (
    CompilationBundle,
    CompilationPassPlan,
    CompilationPassResult,
    CompiledDetailCoverage,
    CoverageGap,
    CoverageReport,
    ObservedDetail,
    SourceManifest,
    WikiIntegrationPlan,
    WikiPagePlan,
)
from backend.app.domain.extraction import IngestExtractionResult
from backend.app.domain.graph import GraphBuildCommand, GraphBuildResult
from backend.app.domain.models import SourceRef, WikiPage
from backend.app.repositories.compiler import SQLiteCompilerRepository
from backend.app.repositories.extractions import SQLiteExtractionRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.repositories.wiki import SQLiteWikiRepository
from backend.app.services.artifact_projector import ArtifactProjector
from backend.app.services.compilation_merger import CompilationMerger
from backend.app.services.compilation_validator import CompilationValidator
from backend.app.services.compiler_contracts import CompilerLLMClient
from backend.app.services.coverage_gate import CoverageGate
from backend.app.services.graph_builder import GraphBuilder
from backend.app.services.knowledge_page_writer import KnowledgePageWriter
from backend.app.services.manifest_planner import ManifestPlanner
from backend.app.services.semantic_indexer import SemanticIndexer, SemanticIndexResult
from backend.app.services.source_page_writer import SourcePageWriter
from backend.app.services.wiki_log import WikiLogWriter


@dataclass(frozen=True)
class SourceIngestResult:
    source: SourceRef
    extraction: IngestExtractionResult
    page: WikiPage
    wiki_pages: list[WikiPage]
    compiler_run_id: str
    manifest: SourceManifest
    compilation: CompilationBundle
    coverage: CoverageReport
    graph: GraphBuildResult
    semantic_index: SemanticIndexResult | None
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
        knowledge_page_writer: KnowledgePageWriter,
        wiki_repository: SQLiteWikiRepository,
        wiki_log_writer: WikiLogWriter,
        max_file_bytes: int,
        model: str,
        compiler_version: str,
        prompt_version: str,
        schema_version: str,
        max_passes: int = 4,
        max_pass_retries: int = 1,
        max_audit_iterations: int = 2,
        merger: CompilationMerger | None = None,
        validator: CompilationValidator | None = None,
        projector: ArtifactProjector | None = None,
        coverage_gate: CoverageGate | None = None,
        manifest_planner: ManifestPlanner | None = None,
        semantic_indexer: SemanticIndexer | None = None,
    ) -> None:
        self.source_repository = source_repository
        self.compiler_repository = compiler_repository
        self.extraction_repository = extraction_repository
        self.job_repository = job_repository
        self.llm_client = llm_client
        self.graph_builder = graph_builder
        self.source_page_writer = source_page_writer
        self.knowledge_page_writer = knowledge_page_writer
        self.wiki_repository = wiki_repository
        self.wiki_log_writer = wiki_log_writer
        self.max_file_bytes = max_file_bytes
        self.model = model
        self.compiler_version = compiler_version
        self.prompt_version = prompt_version
        self.schema_version = schema_version
        if max_passes < 1:
            raise ValueError("Compiler max_passes must be at least 1.")
        self.max_passes = max_passes
        self.max_pass_retries = max_pass_retries
        self.max_audit_iterations = max_audit_iterations
        self.merger = merger or CompilationMerger()
        self.validator = validator or CompilationValidator()
        self.projector = projector or ArtifactProjector()
        self.coverage_gate = coverage_gate or CoverageGate()
        self.manifest_planner = manifest_planner or ManifestPlanner()
        self.semantic_indexer = semantic_indexer

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
            manifest = self.manifest_planner.ensure_complete_plan(
                await self.llm_client.profile_source(source),
                max_passes=self._initial_plan_budget(),
            )
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
            for plan in self._initial_compilation_plans(manifest):
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

            compilation, coverage, executed_passes = await self._audit_and_fill_gaps(
                source,
                run_id,
                manifest,
                compilation,
                executed_passes,
            )
            self.validator.validate(manifest, compilation)
            wiki_plan = await self._plan_wiki(source, manifest, compilation)

            self.compiler_repository.update_stage(
                run_id,
                source.id,
                "integrating",
                utc_now_iso(),
            )
            previous_wiki_paths = self.wiki_repository.list_source_page_paths(source.id)
            extraction = self.projector.project(source, manifest, compilation)
            page = self.source_page_writer.write(
                source,
                extraction,
                compilation=compilation,
                coverage_status=coverage.coverage_status,
                compiler_version=self.compiler_version,
            )
            self.extraction_repository.save(
                source,
                extraction,
                page,
                compiler_run_id=run_id,
            )
            self.compiler_repository.save_artifacts(
                run_id,
                source,
                compilation,
                utc_now_iso(),
            )
            knowledge_pages = self.knowledge_page_writer.write(
                source=source,
                manifest=manifest,
                compilation=compilation,
                plan=wiki_plan,
                coverage_status=coverage.coverage_status,
                compiler_version=self.compiler_version,
            )
            all_wiki_pages = [page, *knowledge_pages]
            self.wiki_repository.save_pages(source.id, all_wiki_pages)
            current_paths = {str(item.path) for item in all_wiki_pages}
            for stale_path in previous_wiki_paths:
                if stale_path not in current_paths:
                    Path(stale_path).unlink(missing_ok=True)
            self.compiler_repository.update_stage(
                run_id,
                source.id,
                "graphing",
                utc_now_iso(),
            )
            graph = await self.graph_builder.build(
                GraphBuildCommand(source_ids=[source.id], rebuild=True)
            )
            semantic_index = None
            if self.semantic_indexer is not None:
                self.compiler_repository.update_stage(
                    run_id,
                    source.id,
                    "indexing",
                    utc_now_iso(),
                )
                semantic_index = await self.semantic_indexer.index_source(source.id)
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
                wiki_pages=all_wiki_pages,
                compiler_run_id=run_id,
                manifest=manifest,
                compilation=compilation,
                coverage=coverage,
                graph=graph,
                semantic_index=semantic_index,
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
                result = self._normalize_pass_result(
                    manifest,
                    current_plan,
                    compilation,
                    result,
                )
                merged = self.merger.merge(compilation, result)
                self.validator.validate_pass(
                    manifest,
                    current_plan,
                    result,
                    merged,
                    require_target_coverage=False,
                )
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
                            "artifact và statement phải có evidence_local_ids hợp lệ. "
                            "Mọi ledger_items và target_detail_ids phải có detail_coverage; "
                            "nếu chưa thể biên dịch đủ, trả detail_coverage status `missing`, "
                            "`weak` hoặc `ambiguous` thay vì bỏ trống."
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
        compilation = self._promote_audit_details(compilation, report)
        report = self.coverage_gate.reconcile(
            manifest,
            compilation,
            report,
            iteration=0,
        )
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
            if executed_passes >= self.max_passes:
                break
            repair_plan = self._repair_plan_from_gaps(
                manifest,
                report.missing_or_weak_areas,
                iteration,
            )
            if repair_plan is None:
                break
            compilation = await self._execute_pass(
                source,
                run_id,
                manifest,
                repair_plan,
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
            compilation = self._promote_audit_details(compilation, report)
            report = self.coverage_gate.reconcile(
                manifest,
                compilation,
                report,
                iteration=iteration,
            )
            self.compiler_repository.save_coverage(
                run_id,
                source.id,
                iteration,
                report,
                utc_now_iso(),
            )
        return compilation, report, executed_passes

    async def _plan_wiki(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        compilation: CompilationBundle,
    ) -> WikiIntegrationPlan:
        last_error: Exception | None = None
        for _ in range(self.max_pass_retries + 1):
            try:
                plan = await self.llm_client.plan_wiki_integration(
                    source,
                    manifest,
                    compilation,
                )
                self.validator.validate_wiki_plan(compilation, plan)
                return plan
            except Exception as exc:
                last_error = exc
        if not compilation.artifacts:
            raise ValueError("Cannot plan wiki integration without artifacts.") from last_error
        return WikiIntegrationPlan(
            pages=[
                WikiPagePlan(
                    local_id="compiled_knowledge",
                    title=f"Tri thức biên dịch từ {source.title}",
                    page_type="compiled_knowledge",
                    summary=manifest.document_profile.summary,
                    artifact_local_ids=[
                        artifact.local_id for artifact in compilation.artifacts
                    ],
                    related_page_local_ids=[],
                    confidence=min(
                        artifact.confidence for artifact in compilation.artifacts
                    ),
                    review_status="unreviewed",
                )
            ],
            notes=[
                "Fallback deterministic page plan used after invalid LLM wiki plans.",
                str(last_error) if last_error else "",
            ],
        )

    @staticmethod
    def _primary_compilation_plan(manifest: SourceManifest) -> CompilationPassPlan:
        return CompilationPassPlan(
            pass_id="primary_full_source_compile",
            objective=(
                "Deep-compile toàn bộ source thành knowledge wiki IR. Dùng manifest như bản "
                "đồ điều hướng, nhưng không giới hạn ở observed detail inventory: nếu raw "
                "source có factual detail độc lập mà manifest bỏ sót, hãy khai báo trong "
                "discovered_details và biên dịch thành evidence, artifact, atomic statement "
                "và detail_coverage. Không dựa vào keyword, regex, fixed chunk hay taxonomy "
                "domain cố định."
            ),
            target_unit_ids=[unit.local_id for unit in manifest.content_units],
            target_detail_ids=[
                detail.local_id for detail in manifest.observed_details
            ],
            expected_outputs=[
                "source unit ledger items for independently queryable factual details",
                "source-grounded evidence",
                "open artifacts with source-backed content",
                "atomic statements for factual details",
                "discovered details for source facts omitted by the manifest",
                "detail coverage mapped to evidence/artifact/statement refs",
                "semantic nodes and artifact relations when present",
                "review items for unresolved ambiguity or low-confidence merges",
            ],
        )

    def _initial_plan_budget(self) -> int:
        if self.max_passes <= 1 or self.max_audit_iterations <= 1:
            return self.max_passes
        return self.max_passes - 1

    def _initial_compilation_plans(
        self,
        manifest: SourceManifest,
    ) -> list[CompilationPassPlan]:
        plans = manifest.compilation_plan or [self._primary_compilation_plan(manifest)]
        return [self._strengthen_initial_plan(plan) for plan in plans]

    @staticmethod
    def _promote_audit_details(
        compilation: CompilationBundle,
        report: CoverageReport,
    ) -> CompilationBundle:
        if not report.additional_details:
            return compilation
        merged = {detail.local_id: detail for detail in compilation.ledger_items}
        merged.update({detail.local_id: detail for detail in report.additional_details})
        return compilation.model_copy(
            update={
                "ledger_items": [merged[key] for key in sorted(merged)],
            }
        )

    @staticmethod
    def _normalize_pass_result(
        manifest: SourceManifest,
        plan: CompilationPassPlan,
        existing: CompilationBundle,
        result: CompilationPassResult,
    ) -> CompilationPassResult:
        unit_by_id = {unit.local_id: unit for unit in manifest.content_units}
        known_details = {
            detail.local_id: detail
            for detail in [
                *manifest.observed_details,
                *existing.ledger_items,
                *existing.discovered_details,
                *result.ledger_items,
                *result.discovered_details,
            ]
        }
        ledger_by_id = {item.local_id: item for item in result.ledger_items}
        for detail_id in plan.target_detail_ids:
            detail = known_details.get(detail_id)
            if detail is not None and detail_id not in ledger_by_id:
                ledger_by_id[detail_id] = detail
        ledger_units = {
            item.source_unit_id
            for item in ledger_by_id.values()
            if item.source_unit_id in set(plan.target_unit_ids)
        }
        for unit_id in plan.target_unit_ids:
            if unit_id in ledger_units:
                continue
            carried_details = [
                detail
                for detail in known_details.values()
                if detail.source_unit_id == unit_id
            ]
            if carried_details:
                for detail in carried_details:
                    ledger_by_id.setdefault(detail.local_id, detail)
                continue
            unit = unit_by_id.get(unit_id)
            if unit is None:
                continue
            ledger_by_id[f"ledger_{unit_id}"] = ObservedDetail(
                local_id=f"ledger_{unit_id}",
                source_unit_id=unit_id,
                detail_kind="source_unit_coverage_obligation",
                description=(
                    "Source unit still requires semantic compilation: "
                    f"{unit.summary or unit.label}"
                ),
                locator=unit.locator,
                importance=unit.importance,
                query_hint=unit.summary or unit.label,
            )
        normalized_ledger = [ledger_by_id[key] for key in sorted(ledger_by_id)]
        detail_ids = {
            detail.local_id
            for detail in [
                *manifest.observed_details,
                *existing.ledger_items,
                *existing.discovered_details,
                *normalized_ledger,
                *result.discovered_details,
            ]
        }
        required_detail_ids = [
            *[item.local_id for item in normalized_ledger],
            *[detail_id for detail_id in plan.target_detail_ids if detail_id in detail_ids],
        ]
        required_detail_ids = list(dict.fromkeys(required_detail_ids))
        covered_detail_ids = {item.detail_id for item in result.detail_coverage}
        missing_coverage = [
            detail_id
            for detail_id in required_detail_ids
            if detail_id not in covered_detail_ids
        ]
        if not missing_coverage and normalized_ledger == result.ledger_items:
            return result
        normalized_coverage = [
            *result.detail_coverage,
            *[
                CompiledDetailCoverage(
                    detail_id=detail_id,
                    status="missing",
                    evidence_local_ids=[],
                    artifact_local_ids=[],
                    statement_refs=[],
                    notes=(
                        "Compiler pass omitted detail_coverage for this source detail; "
                        "normalized as missing so coverage audit and repair can target it."
                    ),
                    confidence=0.0,
                )
                for detail_id in missing_coverage
            ],
        ]
        notes = [
            *result.notes,
        ]
        if normalized_ledger != result.ledger_items:
            notes.append(
                "Normalized pass ledger from manifest/existing source details for "
                "target units/details that the compiler pass omitted."
            )
        if missing_coverage:
            notes.append(
                "Normalized missing detail_coverage entries for source detail IDs: "
                + ", ".join(missing_coverage)
            )
        return result.model_copy(
            update={
                "ledger_items": normalized_ledger,
                "detail_coverage": normalized_coverage,
                "notes": list(dict.fromkeys(notes)),
            }
        )

    @staticmethod
    def _strengthen_initial_plan(plan: CompilationPassPlan) -> CompilationPassPlan:
        expected_outputs = list(
            dict.fromkeys(
                [
                    *plan.expected_outputs,
                    "source unit ledger items for every independently queryable factual detail",
                    "source-close evidence for every target unit",
                    "atomic statements for each independently queryable factual detail",
                    "discovered details for source facts omitted by the manifest",
                    "detail coverage mapped to evidence/artifact/statement refs",
                ]
            )
        )
        return plan.model_copy(
            update={
                "objective": (
                    f"{plan.objective}\n\n"
                    "Deep-compile the targeted semantic source units as durable wiki "
                    "knowledge. First create ledger_items for every independently "
                    "queryable/checkable factual detail in each target unit. Keep "
                    "source-specific conditions, scopes, exceptions, formulas, "
                    "procedures, consequences, rights and obligations when they are "
                    "present in the target units; do not collapse the pass into a broad "
                    "summary. If the source contains factual details not listed in "
                    "observed_details, add them as ledger_items and discovered_details "
                    "and compile them with provenance."
                ),
                "expected_outputs": expected_outputs,
            }
        )

    @staticmethod
    def _repair_plan_from_gaps(
        manifest: SourceManifest,
        gaps: list[CoverageGap],
        iteration: int,
    ) -> CompilationPassPlan | None:
        if not gaps:
            return None
        unit_order = [unit.local_id for unit in manifest.content_units]
        detail_order = [detail.local_id for detail in manifest.observed_details]
        target_units = {
            unit_id
            for gap in gaps
            for unit_id in gap.recommended_pass.target_unit_ids
        }
        target_details = {
            detail_id
            for gap in gaps
            for detail_id in gap.recommended_pass.target_detail_ids
        }
        if not target_units:
            return None
        descriptions = [gap.description for gap in gaps]
        expected_outputs = [
            output
            for gap in gaps
            for output in gap.recommended_pass.expected_outputs
        ]
        expected_outputs = list(
            dict.fromkeys(
                [
                    *expected_outputs,
                    "grounded evidence for missing or weak areas",
                    "source unit ledger items for recovered source details",
                    "discovered details for source facts omitted by the manifest",
                    "artifact additions or enrichments",
                    "atomic statements for recovered details",
                    "detail coverage with evidence/artifact/statement refs",
                    "review items for unresolved ambiguity",
                ]
            )
        )
        return CompilationPassPlan(
            pass_id=f"selective_repair_{iteration}",
            objective=(
                "Thực hiện một repair pass chọn lọc cho các coverage gap đã được audit/gate "
                "xác nhận. Không biên dịch lại mọi thứ nếu existing_compilation đã đủ; chỉ "
                "bổ sung hoặc enrich phần thiếu/yếu, giữ local_id hiện có khi cùng semantic "
                "identity.\n\nCoverage gaps:\n- "
                + "\n- ".join(descriptions)
            ),
            target_unit_ids=_ordered(target_units, unit_order),
            target_detail_ids=_ordered(target_details, detail_order),
            expected_outputs=expected_outputs,
        )


def _ordered(values: set[str], order: list[str]) -> list[str]:
    order_index = {value: index for index, value in enumerate(order)}
    return sorted(values, key=lambda value: order_index.get(value, len(order)))
