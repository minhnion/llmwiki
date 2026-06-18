from backend.app.domain.compiler import (
    CompilationBundle,
    CoverageGap,
    CoverageReport,
    CoverageUnitAssessment,
    RecommendedCompilationPass,
    SourceManifest,
)
from backend.app.services.compilation_validator import CompilationValidator


class CoverageGateError(ValueError):
    pass


class CoverageGate:
    """Reconciles model judgment with deterministic provenance coverage."""

    def reconcile(
        self,
        manifest: SourceManifest,
        compilation: CompilationBundle,
        report: CoverageReport,
        iteration: int,
    ) -> CoverageReport:
        unit_ids = {unit.local_id for unit in manifest.content_units}
        assessment_ids = [assessment.unit_id for assessment in report.unit_assessments]
        unknown = set(assessment_ids) - unit_ids
        missing = unit_ids - set(assessment_ids)
        if unknown:
            raise CoverageGateError(
                f"Coverage report references unknown units: {sorted(unknown)}"
            )
        if missing:
            raise CoverageGateError(
                f"Coverage report did not assess source units: {sorted(missing)}"
            )
        if len(assessment_ids) != len(set(assessment_ids)):
            raise CoverageGateError("Coverage report contains duplicate unit assessments.")

        valid_gaps: list[CoverageGap] = []
        for gap in report.missing_or_weak_areas:
            gap_units = set(gap.likely_unit_ids)
            pass_units = set(gap.recommended_pass.target_unit_ids)
            unknown_gap_units = (gap_units | pass_units) - unit_ids
            if unknown_gap_units:
                raise CoverageGateError(
                    f"Coverage gap references unknown units: {sorted(unknown_gap_units)}"
                )
            if not pass_units:
                raise CoverageGateError("Coverage follow-up pass must target source units.")
            valid_gaps.append(gap)

        supported_units = CompilationValidator.supported_unit_ids(compilation)
        assessments_by_unit = {
            assessment.unit_id: assessment
            for assessment in report.unit_assessments
        }
        reconciled_assessments: list[CoverageUnitAssessment] = []
        for unit in manifest.content_units:
            assessment = assessments_by_unit[unit.local_id]
            if unit.local_id in supported_units:
                reconciled_assessments.append(assessment)
                continue
            missing_knowledge = list(assessment.missing_knowledge)
            deterministic_reason = (
                "Không có đủ chuỗi provenance evidence + artifact + atomic statement "
                "cho source unit này."
            )
            if deterministic_reason not in missing_knowledge:
                missing_knowledge.append(deterministic_reason)
            reconciled_assessments.append(
                assessment.model_copy(
                    update={
                        "status": "incomplete",
                        "missing_knowledge": missing_knowledge,
                    }
                )
            )

        gapped_units = {
            unit_id
            for gap in valid_gaps
            for unit_id in gap.recommended_pass.target_unit_ids
        }
        for unit in manifest.content_units:
            if unit.local_id in supported_units or unit.local_id in gapped_units:
                continue
            valid_gaps.append(
                CoverageGap(
                    description=(
                        f"Source unit `{unit.label}` chưa có knowledge representation "
                        "được provenance gate xác nhận."
                    ),
                    likely_unit_ids=[unit.local_id],
                    severity="high" if unit.importance >= 0.8 else "medium",
                    recommended_pass=RecommendedCompilationPass(
                        pass_id=f"coverage_follow_up_{iteration}_{unit.local_id}",
                        objective=(
                            f"Biên dịch đầy đủ source unit `{unit.label}`. Tạo evidence, "
                            "artifact và atomic statements có source_unit_ids nhất quán; "
                            "giữ mọi điều kiện, ngoại lệ, số liệu và quan hệ quan trọng."
                        ),
                        target_unit_ids=[unit.local_id],
                        expected_outputs=[
                            "grounded evidence",
                            "source-backed artifact",
                            "atomic statements",
                            "semantic nodes and relations when present",
                        ],
                    ),
                )
            )

        has_incomplete_assessment = any(
            assessment.status != "complete" or assessment.missing_knowledge
            for assessment in reconciled_assessments
        )
        has_quality_issue = bool(
            valid_gaps
            or report.provenance_issues
            or report.overgeneralization_risks
        )
        if supported_units == unit_ids and not has_incomplete_assessment and not has_quality_issue:
            status = "complete"
        elif valid_gaps or has_incomplete_assessment:
            status = "incomplete"
        else:
            status = "needs_review"

        return report.model_copy(
            update={
                "coverage_status": status,
                "covered_unit_ids": sorted(supported_units),
                "unit_assessments": reconciled_assessments,
                "missing_or_weak_areas": valid_gaps,
            }
        )

    def validate_report(
        self,
        manifest: SourceManifest,
        report: CoverageReport,
        compilation: CompilationBundle | None = None,
        iteration: int = 0,
    ) -> CoverageReport:
        if compilation is None:
            compilation = CompilationBundle(
                evidence_items=[],
                artifacts=[],
                semantic_nodes=[],
                relations=[],
                review_items=[],
                covered_unit_ids=[],
                notes=[],
            )
        return self.reconcile(manifest, compilation, report, iteration)
