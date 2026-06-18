from backend.app.domain.compiler import CoverageReport, SourceManifest


class CoverageGateError(ValueError):
    pass


class CoverageGate:
    def validate_report(
        self,
        manifest: SourceManifest,
        report: CoverageReport,
    ) -> None:
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

        if report.coverage_status != "complete":
            return
        incomplete = [
            assessment.unit_id
            for assessment in report.unit_assessments
            if assessment.status != "complete" or assessment.missing_knowledge
        ]
        if incomplete:
            raise CoverageGateError(
                "Coverage cannot be complete while units remain incomplete: "
                f"{sorted(incomplete)}"
            )
        if report.missing_or_weak_areas:
            raise CoverageGateError(
                "Coverage cannot be complete while missing_or_weak_areas is non-empty."
            )
        if report.provenance_issues:
            raise CoverageGateError(
                "Coverage cannot be complete while provenance issues remain."
            )
