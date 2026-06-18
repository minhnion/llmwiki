from backend.app.domain.compiler import CompilationBundle, SourceManifest


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
        valid_unit_ids = {unit.local_id for unit in manifest.content_units}
        unknown_covered_units = set(bundle.covered_unit_ids) - valid_unit_ids
        if unknown_covered_units:
            raise CompilationValidationError(
                f"Compilation covers unknown source units: {sorted(unknown_covered_units)}"
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
            if not artifact.evidence_local_ids:
                raise CompilationValidationError(
                    f"Source-backed artifact {artifact.local_id} has no evidence."
                )
            for statement in artifact.statements:
                self._require_refs(
                    statement.evidence_local_ids,
                    evidence_ids,
                    f"statement in artifact {artifact.local_id}",
                )
                if not statement.evidence_local_ids:
                    raise CompilationValidationError(
                        f"Statement in artifact {artifact.local_id} has no evidence."
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
