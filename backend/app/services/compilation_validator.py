from backend.app.domain.compiler import (
    CompilationBundle,
    CompilationPassPlan,
    CompilationPassResult,
    SourceManifest,
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
    ) -> None:
        self.validate(manifest, merged)
        if result.pass_id != plan.pass_id:
            raise CompilationValidationError(
                f"Compilation result pass_id {result.pass_id} != {plan.pass_id}."
            )
        missing_targets = set(plan.target_unit_ids) - self.supported_unit_ids(merged)
        if missing_targets:
            raise CompilationValidationError(
                f"Compilation pass {plan.pass_id} did not produce grounded knowledge for "
                f"target units: {sorted(missing_targets)}"
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

    @staticmethod
    def _require_refs(refs: list[str], valid: set[str], label: str) -> None:
        unknown = set(refs) - valid
        if unknown:
            raise CompilationValidationError(
                f"{label} references unknown IDs: {sorted(unknown)}"
            )


def _unique_ids(values: list[str], label: str) -> set[str]:
    if any(not value.strip() for value in values):
        raise CompilationValidationError(f"{label} local IDs must not be empty.")
    if len(values) != len(set(values)):
        raise CompilationValidationError(f"{label} local IDs must be unique.")
    return set(values)
