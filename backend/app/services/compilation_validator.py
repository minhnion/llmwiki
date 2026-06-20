from backend.app.domain.compiler import (
    CompilationBundle,
    CompilationPassPlan,
    CompilationPassResult,
    CompiledDetailCoverage,
    ObservedDetail,
    SourceManifest,
    StatementReference,
    WikiIntegrationPlan,
)


class CompilationValidationError(ValueError):
    pass


class CompilationValidator:
    def validate(self, manifest: SourceManifest, bundle: CompilationBundle) -> None:
        evidence_ids = _unique_ids(
            [item.local_id for item in bundle.evidence_items],
            "evidence",
        )
        artifact_ids = _unique_ids(
            [item.local_id for item in bundle.artifacts],
            "artifact",
        )
        _unique_ids(
            [item.local_id for item in bundle.semantic_nodes],
            "semantic node",
        )
        valid_unit_ids = {unit.local_id for unit in manifest.content_units}
        detail_unit_by_id = self._detail_unit_map(manifest, bundle)
        valid_detail_ids = set(detail_unit_by_id)
        self._validate_compiled_detail_inventory(manifest, bundle)
        unknown_covered_units = set(bundle.covered_unit_ids) - valid_unit_ids
        if unknown_covered_units:
            raise CompilationValidationError(
                f"Compilation covers unknown source units: {sorted(unknown_covered_units)}"
            )

        evidence_units = {
            evidence.local_id: set(evidence.source_unit_ids)
            for evidence in bundle.evidence_items
        }
        for evidence in bundle.evidence_items:
            self._require_refs(
                evidence.source_unit_ids,
                valid_unit_ids,
                f"evidence {evidence.local_id} source units",
            )
            if not evidence.source_unit_ids:
                raise CompilationValidationError(
                    f"Evidence {evidence.local_id} has no source_unit_ids."
                )

        for artifact in bundle.artifacts:
            self._require_refs(
                artifact.evidence_local_ids,
                evidence_ids,
                f"artifact {artifact.local_id}",
            )
            self._require_refs(
                artifact.related_artifact_local_ids,
                artifact_ids,
                f"artifact {artifact.local_id} related artifacts",
            )
            self._require_refs(
                artifact.source_unit_ids,
                valid_unit_ids,
                f"artifact {artifact.local_id} source units",
            )
            if not artifact.evidence_local_ids:
                raise CompilationValidationError(
                    f"Source-backed artifact {artifact.local_id} has no evidence."
                )
            if not artifact.source_unit_ids:
                raise CompilationValidationError(
                    f"Artifact {artifact.local_id} has no source_unit_ids."
                )
            if not artifact.statements:
                raise CompilationValidationError(
                    f"Artifact {artifact.local_id} has no atomic statements."
                )
            artifact_evidence_units = {
                unit_id
                for evidence_local_id in artifact.evidence_local_ids
                for unit_id in evidence_units[evidence_local_id]
            }
            if not set(artifact.source_unit_ids) <= artifact_evidence_units:
                raise CompilationValidationError(
                    f"Artifact {artifact.local_id} source units are not supported by "
                    "its evidence."
                )
            _unique_ids(
                [statement.local_id for statement in artifact.statements],
                f"statement in artifact {artifact.local_id}",
            )
            for statement in artifact.statements:
                self._require_refs(
                    statement.evidence_local_ids,
                    evidence_ids,
                    f"statement {statement.local_id}",
                )
                self._require_refs(
                    statement.source_unit_ids,
                    valid_unit_ids,
                    f"statement {statement.local_id} source units",
                )
                if not statement.evidence_local_ids:
                    raise CompilationValidationError(
                        f"Statement {statement.local_id} has no evidence."
                    )
                if not statement.source_unit_ids:
                    raise CompilationValidationError(
                        f"Statement {statement.local_id} has no source_unit_ids."
                    )
                if not set(statement.source_unit_ids) <= set(artifact.source_unit_ids):
                    raise CompilationValidationError(
                        f"Statement {statement.local_id} references source units outside "
                        f"artifact {artifact.local_id}."
                    )
                statement_evidence_units = {
                    unit_id
                    for evidence_local_id in statement.evidence_local_ids
                    for unit_id in evidence_units[evidence_local_id]
                }
                if not set(statement.source_unit_ids) <= statement_evidence_units:
                    raise CompilationValidationError(
                        f"Statement {statement.local_id} source units are not supported "
                        "by its evidence."
                    )

        statements_by_artifact = {
            artifact.local_id: {statement.local_id for statement in artifact.statements}
            for artifact in bundle.artifacts
        }
        detail_ids = _unique_ids(
            [item.detail_id for item in bundle.detail_coverage],
            "compiled detail coverage",
        )
        self._require_refs(detail_ids, valid_detail_ids, "compiled detail coverage")
        for detail in bundle.detail_coverage:
            self._validate_detail_coverage(
                detail,
                evidence_ids,
                artifact_ids,
                statements_by_artifact,
            )

        for node in bundle.semantic_nodes:
            self._require_refs(
                node.evidence_local_ids,
                evidence_ids,
                f"semantic node {node.local_id}",
            )
            self._require_refs(
                node.source_unit_ids,
                valid_unit_ids,
                f"semantic node {node.local_id} source units",
            )
            if not node.evidence_local_ids or not node.source_unit_ids:
                raise CompilationValidationError(
                    f"Semantic node {node.local_id} lacks provenance."
                )

        for relation in bundle.relations:
            self._require_refs(
                [relation.source_artifact_local_id],
                artifact_ids,
                "artifact relation source",
            )
            if relation.target_artifact_local_id:
                self._require_refs(
                    [relation.target_artifact_local_id],
                    artifact_ids,
                    "artifact relation target",
                )
            if not relation.target_artifact_local_id and not relation.target_literal.strip():
                raise CompilationValidationError(
                    "Artifact relation must have a target artifact or literal."
                )
            self._require_refs(
                relation.evidence_local_ids,
                evidence_ids,
                "artifact relation evidence",
            )
            if not relation.evidence_local_ids:
                raise CompilationValidationError("Artifact relation has no evidence.")

        for review in bundle.review_items:
            self._require_refs(
                review.evidence_local_ids,
                evidence_ids,
                f"review item {review.title}",
            )
            self._require_refs(
                review.artifact_local_ids,
                artifact_ids,
                f"review item {review.title}",
            )

        actual_covered_units = self.supported_unit_ids(bundle)
        if set(bundle.covered_unit_ids) != actual_covered_units:
            raise CompilationValidationError(
                "covered_unit_ids must be derived from evidence + artifact + statement "
                f"provenance; expected {sorted(actual_covered_units)}."
            )

    def validate_pass(
        self,
        manifest: SourceManifest,
        plan: CompilationPassPlan,
        result: CompilationPassResult,
        merged: CompilationBundle,
        require_target_coverage: bool = True,
    ) -> None:
        self.validate(manifest, merged)
        if result.pass_id != plan.pass_id:
            raise CompilationValidationError(
                f"Compilation result pass_id {result.pass_id} != {plan.pass_id}."
            )
        self._validate_pass_ledger(manifest, plan, result)
        if not require_target_coverage:
            return
        missing_targets = set(plan.target_unit_ids) - self.supported_unit_ids(merged)
        if missing_targets:
            raise CompilationValidationError(
                f"Compilation pass {plan.pass_id} did not produce grounded knowledge for "
                f"target units: {sorted(missing_targets)}"
            )
        missing_details = set(plan.target_detail_ids) - self.supported_detail_ids(
            merged,
            manifest,
        )
        if missing_details:
            raise CompilationValidationError(
                f"Compilation pass {plan.pass_id} did not produce grounded knowledge for "
                f"target details: {sorted(missing_details)}"
            )

    def validate_wiki_plan(
        self,
        bundle: CompilationBundle,
        plan: WikiIntegrationPlan,
    ) -> None:
        artifact_ids = {artifact.local_id for artifact in bundle.artifacts}
        represented: set[str] = set()
        for page in plan.pages:
            if not page.artifact_local_ids:
                raise CompilationValidationError(
                    f"Wiki page {page.local_id} has no artifacts."
                )
            self._require_refs(
                page.artifact_local_ids,
                artifact_ids,
                f"wiki page {page.local_id}",
            )
            represented.update(page.artifact_local_ids)
        missing = artifact_ids - represented
        if missing:
            raise CompilationValidationError(
                f"Wiki integration plan omits artifacts: {sorted(missing)}"
            )

    @staticmethod
    def supported_unit_ids(bundle: CompilationBundle) -> set[str]:
        evidence_units = {
            unit_id
            for evidence in bundle.evidence_items
            for unit_id in evidence.source_unit_ids
        }
        artifact_units = {
            unit_id
            for artifact in bundle.artifacts
            for unit_id in artifact.source_unit_ids
        }
        statement_units = {
            unit_id
            for artifact in bundle.artifacts
            for statement in artifact.statements
            for unit_id in statement.source_unit_ids
        }
        return evidence_units & artifact_units & statement_units

    @classmethod
    def supported_detail_ids(
        cls,
        bundle: CompilationBundle,
        manifest: SourceManifest | None = None,
    ) -> set[str]:
        if manifest is None:
            return {
                item.detail_id
                for item in bundle.detail_coverage
                if item.status == "covered"
                and item.evidence_local_ids
                and item.artifact_local_ids
                and item.statement_refs
            }
        return cls._supported_detail_ids_for_manifest(bundle, manifest)

    @staticmethod
    def _require_refs(refs: list[str], valid: set[str], label: str) -> None:
        unknown = set(refs) - valid
        if unknown:
            raise CompilationValidationError(
                f"{label} references unknown IDs: {sorted(unknown)}"
            )

    def _validate_detail_coverage(
        self,
        detail: CompiledDetailCoverage,
        evidence_ids: set[str],
        artifact_ids: set[str],
        statements_by_artifact: dict[str, set[str]],
    ) -> None:
        self._require_refs(
            detail.evidence_local_ids,
            evidence_ids,
            f"detail coverage {detail.detail_id} evidence",
        )
        self._require_refs(
            detail.artifact_local_ids,
            artifact_ids,
            f"detail coverage {detail.detail_id} artifacts",
        )
        for ref in detail.statement_refs:
            self._validate_statement_ref(ref, statements_by_artifact, detail.detail_id)
            if ref.artifact_local_id not in detail.artifact_local_ids:
                raise CompilationValidationError(
                    f"Detail coverage {detail.detail_id} statement ref artifact "
                    "is not listed in artifact_local_ids."
                )
        if detail.status == "covered":
            if not detail.evidence_local_ids:
                raise CompilationValidationError(
                    f"Covered detail {detail.detail_id} has no evidence."
                )
            if not detail.artifact_local_ids:
                raise CompilationValidationError(
                    f"Covered detail {detail.detail_id} has no artifact."
                )
            if not detail.statement_refs:
                raise CompilationValidationError(
                    f"Covered detail {detail.detail_id} has no statement reference."
                )

    @staticmethod
    def _validate_statement_ref(
        ref: StatementReference,
        statements_by_artifact: dict[str, set[str]],
        detail_id: str,
    ) -> None:
        if ref.artifact_local_id not in statements_by_artifact:
            raise CompilationValidationError(
                f"Detail coverage {detail_id} references unknown artifact "
                f"{ref.artifact_local_id}."
            )
        if ref.statement_local_id not in statements_by_artifact[ref.artifact_local_id]:
            raise CompilationValidationError(
                f"Detail coverage {detail_id} references unknown statement "
                f"{ref.statement_local_id} in artifact {ref.artifact_local_id}."
            )

    @staticmethod
    def _detail_unit_map(
        manifest: SourceManifest,
        bundle: CompilationBundle,
    ) -> dict[str, str]:
        detail_units: dict[str, str] = {}
        _add_detail_units(detail_units, manifest.observed_details, "manifest details")
        _add_detail_units(detail_units, bundle.ledger_items, "ledger items")
        _add_detail_units(detail_units, bundle.discovered_details, "discovered details")
        return detail_units

    @staticmethod
    def _validate_compiled_detail_inventory(
        manifest: SourceManifest,
        bundle: CompilationBundle,
    ) -> None:
        valid_unit_ids = {unit.local_id for unit in manifest.content_units}
        unknown_units = {
            detail.source_unit_id
            for detail in [*bundle.ledger_items, *bundle.discovered_details]
            if detail.source_unit_id not in valid_unit_ids
        }
        if unknown_units:
            raise CompilationValidationError(
                "compiled detail inventory references unknown source units: "
                f"{sorted(unknown_units)}"
            )

    @staticmethod
    def _validate_pass_ledger(
        manifest: SourceManifest,
        plan: CompilationPassPlan,
        result: CompilationPassResult,
    ) -> None:
        valid_unit_ids = {unit.local_id for unit in manifest.content_units}
        unknown_units = {
            item.source_unit_id
            for item in result.ledger_items
            if item.source_unit_id not in valid_unit_ids
        }
        if unknown_units:
            raise CompilationValidationError(
                f"Compilation pass {plan.pass_id} ledger references unknown units: "
                f"{sorted(unknown_units)}"
            )
        target_units = set(plan.target_unit_ids)
        ledger_units = {
            item.source_unit_id
            for item in result.ledger_items
            if item.source_unit_id in target_units
        }
        missing_unit_ledgers = target_units - ledger_units
        if missing_unit_ledgers:
            raise CompilationValidationError(
                f"Compilation pass {plan.pass_id} did not produce ledger items for "
                f"target units: {sorted(missing_unit_ledgers)}"
            )
        ledger_ids = [item.local_id for item in result.ledger_items]
        if len(ledger_ids) != len(set(ledger_ids)):
            raise CompilationValidationError(
                f"Compilation pass {plan.pass_id} contains duplicate ledger item IDs."
            )
        coverage_ids = {item.detail_id for item in result.detail_coverage}
        missing_coverage = set(ledger_ids) - coverage_ids
        if missing_coverage:
            raise CompilationValidationError(
                f"Compilation pass {plan.pass_id} ledger items lack detail_coverage: "
                f"{sorted(missing_coverage)}"
            )

    @classmethod
    def _supported_detail_ids_for_manifest(
        cls,
        bundle: CompilationBundle,
        manifest: SourceManifest,
    ) -> set[str]:
        detail_unit_by_id = cls._detail_unit_map(manifest, bundle)
        evidence_units = {
            evidence.local_id: set(evidence.source_unit_ids)
            for evidence in bundle.evidence_items
        }
        artifact_units = {
            artifact.local_id: set(artifact.source_unit_ids)
            for artifact in bundle.artifacts
        }
        statement_units_by_ref = {
            (artifact.local_id, statement.local_id): set(statement.source_unit_ids)
            for artifact in bundle.artifacts
            for statement in artifact.statements
        }
        return {
            detail.detail_id
            for detail in bundle.detail_coverage
            if detail.status == "covered"
            and detail.evidence_local_ids
            and detail.artifact_local_ids
            and detail.statement_refs
            and detail.detail_id in detail_unit_by_id
            and cls._has_source_unit_support(
                detail,
                detail_unit_by_id[detail.detail_id],
                evidence_units,
                artifact_units,
                statement_units_by_ref,
            )
        }

    @staticmethod
    def _has_source_unit_support(
        detail: CompiledDetailCoverage,
        source_unit_id: str,
        evidence_units: dict[str, set[str]],
        artifact_units: dict[str, set[str]],
        statement_units_by_ref: dict[tuple[str, str], set[str]],
    ) -> bool:
        return (
            any(
                source_unit_id in evidence_units.get(evidence_id, set())
                for evidence_id in detail.evidence_local_ids
            )
            and any(
                source_unit_id in artifact_units.get(artifact_id, set())
                for artifact_id in detail.artifact_local_ids
            )
            and any(
                source_unit_id
                in statement_units_by_ref.get(
                    (ref.artifact_local_id, ref.statement_local_id),
                    set(),
                )
                for ref in detail.statement_refs
            )
        )


def _unique_ids(values: list[str], label: str) -> set[str]:
    if any(not value.strip() for value in values):
        raise CompilationValidationError(f"{label} local IDs must not be empty.")
    if len(values) != len(set(values)):
        raise CompilationValidationError(f"{label} local IDs must be unique.")
    return set(values)


def _add_detail_units(
    detail_units: dict[str, str],
    details: list[ObservedDetail],
    label: str,
) -> None:
    ids = [detail.local_id for detail in details]
    if len(ids) != len(set(ids)):
        raise CompilationValidationError(f"{label} local IDs must be unique.")
    for detail in details:
        existing_unit = detail_units.get(detail.local_id)
        if existing_unit is not None and existing_unit != detail.source_unit_id:
            raise CompilationValidationError(
                f"{label} detail {detail.local_id} conflicts with existing source unit "
                f"{existing_unit}."
            )
        detail_units[detail.local_id] = detail.source_unit_id
