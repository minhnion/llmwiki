from backend.app.domain.compiler import (
    CompilationBundle,
    CoverageDetailAssessment,
    CoverageGap,
    CoverageReport,
    CoverageUnitAssessment,
    ObservedDetail,
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
        details = _all_details(manifest, compilation)
        detail_by_id = {detail.local_id: detail for detail in details}
        assessments_by_unit = self._validate_unit_assessments(manifest, report)
        assessments_by_detail = self._validate_detail_assessments(details, report)
        valid_gaps = self._normalize_gaps(
            manifest,
            details,
            report.missing_or_weak_areas,
        )

        supported_units = CompilationValidator.supported_unit_ids(compilation)
        supported_details = CompilationValidator.supported_detail_ids(
            compilation,
            manifest,
        )
        compiled_details = {
            item.detail_id: item for item in compilation.detail_coverage
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

        reconciled_detail_assessments: list[CoverageDetailAssessment] = []
        for detail in details:
            assessment = assessments_by_detail[detail.local_id]
            if detail.local_id in supported_details:
                reconciled_detail_assessments.append(assessment)
                continue
            compiled_detail = compiled_details.get(detail.local_id)
            missing_knowledge = list(assessment.missing_knowledge)
            deterministic_reason = (
                "Không có đủ chuỗi provenance evidence + artifact + atomic statement "
                "cho source detail này."
            )
            if deterministic_reason not in missing_knowledge:
                missing_knowledge.append(deterministic_reason)
            status = (
                compiled_detail.status
                if compiled_detail is not None
                and compiled_detail.status in {"weak", "ambiguous"}
                else "missing"
            )
            reconciled_detail_assessments.append(
                assessment.model_copy(
                    update={
                        "status": status,
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
            assessment = assessments_by_unit[unit.local_id]
            needs_repair = (
                unit.local_id not in supported_units
                or assessment.status != "complete"
                or bool(assessment.missing_knowledge)
            )
            if not needs_repair or unit.local_id in gapped_units:
                continue
            valid_gaps.append(
                CoverageGap(
                    description=(
                        f"Source unit `{unit.label}` chưa được coverage gate xác nhận "
                        "đầy đủ."
                    ),
                    likely_unit_ids=[unit.local_id],
                    severity="high" if unit.importance >= 0.8 else "medium",
                    recommended_pass=RecommendedCompilationPass(
                        pass_id=f"coverage_follow_up_{iteration}_{unit.local_id}",
                        objective=(
                            f"Biên dịch đầy đủ source unit `{unit.label}`. Tạo evidence, "
                            "artifact và atomic statements có source_unit_ids nhất quán; "
                            "giữ các chi tiết quan trọng theo chính ngữ cảnh source."
                        ),
                        target_unit_ids=[unit.local_id],
                        expected_outputs=[
                            "grounded evidence",
                            "source-backed artifact",
                            "atomic statements",
                            "detail coverage for source ledger details",
                            "semantic nodes and relations when present",
                        ],
                    ),
                )
            )

        gapped_details = {
            detail_id
            for gap in valid_gaps
            for detail_id in [
                *gap.likely_detail_ids,
                *gap.recommended_pass.target_detail_ids,
            ]
        }
        detail_assessments_by_id = {
            assessment.detail_id: assessment
            for assessment in reconciled_detail_assessments
        }
        for detail in details:
            assessment = detail_assessments_by_id[detail.local_id]
            needs_repair = (
                detail.local_id not in supported_details
                or assessment.status != "covered"
                or bool(assessment.missing_knowledge)
            )
            if not needs_repair or detail.local_id in gapped_details:
                continue
            valid_gaps.append(
                CoverageGap(
                    description=(
                        f"Source detail `{detail.description}` chưa có knowledge "
                        "representation được provenance gate xác nhận."
                    ),
                    likely_unit_ids=[detail.source_unit_id],
                    likely_detail_ids=[detail.local_id],
                    severity="high" if detail.importance >= 0.8 else "medium",
                    recommended_pass=RecommendedCompilationPass(
                        pass_id=f"coverage_follow_up_{iteration}_{detail.local_id}",
                        objective=(
                            f"Biên dịch source detail `{detail.description}` từ source "
                            "unit tương ứng. Tạo hoặc enrich evidence, artifact và atomic "
                            "statement đủ cụ thể để detail này có thể được truy vấn và cite."
                        ),
                        target_unit_ids=[detail.source_unit_id],
                        target_detail_ids=[detail.local_id],
                        expected_outputs=[
                            "grounded evidence for the source detail",
                            "source-backed artifact or artifact enrichment",
                            "atomic statements for the source detail",
                            "detail coverage with evidence/artifact/statement refs",
                            "review item if the detail remains ambiguous",
                        ],
                    ),
                )
            )

        has_incomplete_assessment = any(
            assessment.status != "complete" or assessment.missing_knowledge
            for assessment in reconciled_assessments
        )
        has_incomplete_detail = any(
            assessment.status != "covered" or assessment.missing_knowledge
            for assessment in reconciled_detail_assessments
        )
        all_details_supported = set(detail_by_id) <= supported_details
        has_quality_issue = bool(
            valid_gaps
            or report.provenance_issues
            or report.overgeneralization_risks
        )
        if (
            supported_units == unit_ids
            and all_details_supported
            and not has_incomplete_assessment
            and not has_incomplete_detail
            and not has_quality_issue
        ):
            status = "complete"
        elif valid_gaps or has_incomplete_assessment or has_incomplete_detail:
            status = "incomplete"
        else:
            status = "needs_review"

        return report.model_copy(
            update={
                "coverage_status": status,
                "covered_unit_ids": sorted(supported_units),
                "unit_assessments": reconciled_assessments,
                "detail_assessments": reconciled_detail_assessments,
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

    @staticmethod
    def _validate_unit_assessments(
        manifest: SourceManifest,
        report: CoverageReport,
    ) -> dict[str, CoverageUnitAssessment]:
        unit_by_id = {unit.local_id: unit for unit in manifest.content_units}
        unit_ids = set(unit_by_id)
        assessment_ids = [assessment.unit_id for assessment in report.unit_assessments]
        missing = unit_ids - set(assessment_ids)
        if len(assessment_ids) != len(set(assessment_ids)):
            raise CoverageGateError("Coverage report contains duplicate unit assessments.")
        assessments = {
            assessment.unit_id: assessment
            for assessment in report.unit_assessments
            if assessment.unit_id in unit_ids
        }
        for unit_id in sorted(missing):
            assessments[unit_id] = CoverageUnitAssessment(
                unit_id=unit_id,
                status="incomplete",
                represented_knowledge=[],
                missing_knowledge=[
                    "Coverage auditor không tạo assessment cho source unit này."
                ],
                confidence=0.0,
            )
        return assessments

    @staticmethod
    def _validate_detail_assessments(
        details: list[ObservedDetail],
        report: CoverageReport,
    ) -> dict[str, CoverageDetailAssessment]:
        detail_by_id = {detail.local_id: detail for detail in details}
        assessment_ids = [
            assessment.detail_id for assessment in report.detail_assessments
        ]
        missing = set(detail_by_id) - set(assessment_ids)
        if len(assessment_ids) != len(set(assessment_ids)):
            raise CoverageGateError(
                "Coverage report contains duplicate detail assessments."
            )
        assessments = {
            assessment.detail_id: assessment
            for assessment in report.detail_assessments
            if assessment.detail_id in detail_by_id
        }
        for detail_id, assessment in assessments.items():
            expected_unit_id = detail_by_id[detail_id].source_unit_id
            if assessment.unit_id != expected_unit_id:
                raise CoverageGateError(
                    f"Coverage detail assessment {detail_id} uses unit "
                    f"{assessment.unit_id}, expected {expected_unit_id}."
                )
        for detail_id in sorted(missing):
            detail = detail_by_id[detail_id]
            assessments[detail_id] = CoverageDetailAssessment(
                detail_id=detail_id,
                unit_id=detail.source_unit_id,
                status="missing",
                represented_knowledge=[],
                missing_knowledge=[
                    "Coverage auditor không tạo assessment cho source detail này."
                ],
                evidence_local_ids=[],
                artifact_local_ids=[],
                statement_refs=[],
                confidence=0.0,
            )
        return assessments

    @staticmethod
    def _normalize_gaps(
        manifest: SourceManifest,
        details: list[ObservedDetail],
        gaps: list[CoverageGap],
    ) -> list[CoverageGap]:
        unit_order = [unit.local_id for unit in manifest.content_units]
        unit_ids = set(unit_order)
        detail_by_id = {detail.local_id: detail for detail in details}
        detail_order = [detail.local_id for detail in details]
        valid_gaps: list[CoverageGap] = []
        for gap in gaps:
            likely_details = set(gap.likely_detail_ids)
            pass_details = set(gap.recommended_pass.target_detail_ids)
            unknown_details = (likely_details | pass_details) - set(detail_by_id)
            likely_details -= unknown_details
            pass_details -= unknown_details
            implied_units = {
                detail_by_id[detail_id].source_unit_id
                for detail_id in likely_details | pass_details
            }
            gap_units = set(gap.likely_unit_ids) | implied_units
            pass_units = set(gap.recommended_pass.target_unit_ids) | {
                detail_by_id[detail_id].source_unit_id
                for detail_id in pass_details
            }
            unknown_gap_units = (gap_units | pass_units) - unit_ids
            gap_units -= unknown_gap_units
            pass_units -= unknown_gap_units
            if not pass_units:
                continue
            recommended_pass = gap.recommended_pass.model_copy(
                update={
                    "target_unit_ids": _ordered(pass_units, unit_order),
                    "target_detail_ids": _ordered(pass_details, detail_order),
                }
            )
            valid_gaps.append(
                gap.model_copy(
                    update={
                        "likely_unit_ids": _ordered(gap_units, unit_order),
                        "likely_detail_ids": _ordered(likely_details, detail_order),
                        "recommended_pass": recommended_pass,
                    }
                )
            )
        return valid_gaps


def _ordered(values: set[str], order: list[str]) -> list[str]:
    order_index = {value: index for index, value in enumerate(order)}
    return sorted(values, key=lambda value: order_index.get(value, len(order)))


def _all_details(
    manifest: SourceManifest,
    compilation: CompilationBundle,
) -> list[ObservedDetail]:
    merged = {detail.local_id: detail for detail in manifest.observed_details}
    merged.update({detail.local_id: detail for detail in compilation.ledger_items})
    merged.update({detail.local_id: detail for detail in compilation.discovered_details})
    return [merged[key] for key in sorted(merged)]
