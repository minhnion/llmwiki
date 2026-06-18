from backend.app.domain.compiler import (
    CompilationBundle,
    CompilationPassResult,
    CompiledArtifact,
    CompiledEvidence,
    CompiledRelation,
    CompilerReviewItem,
)


class CompilationMerger:
    def merge(
        self,
        current: CompilationBundle,
        incoming: CompilationPassResult,
    ) -> CompilationBundle:
        evidence = _merge_by_local_id(current.evidence_items, incoming.evidence_items)
        artifacts = _merge_by_local_id(current.artifacts, incoming.artifacts)
        relations = _merge_relations(current.relations, incoming.relations)
        review_items = _merge_review_items(current.review_items, incoming.review_items)
        return CompilationBundle(
            evidence_items=evidence,
            artifacts=artifacts,
            relations=relations,
            review_items=review_items,
            covered_unit_ids=list(
                dict.fromkeys([*current.covered_unit_ids, *incoming.covered_unit_ids])
            ),
            notes=list(dict.fromkeys([*current.notes, *incoming.notes])),
        )

    @staticmethod
    def empty() -> CompilationBundle:
        return CompilationBundle(
            evidence_items=[],
            artifacts=[],
            relations=[],
            review_items=[],
            covered_unit_ids=[],
            notes=[],
        )


def _merge_by_local_id(
    existing: list[CompiledEvidence] | list[CompiledArtifact],
    incoming: list[CompiledEvidence] | list[CompiledArtifact],
) -> list:
    merged = {item.local_id: item for item in existing}
    merged.update({item.local_id: item for item in incoming})
    return [merged[key] for key in sorted(merged)]


def _merge_relations(
    existing: list[CompiledRelation],
    incoming: list[CompiledRelation],
) -> list[CompiledRelation]:
    def key(relation: CompiledRelation) -> tuple[str, str, str, str]:
        return (
            relation.source_artifact_local_id,
            relation.relation_type,
            relation.target_artifact_local_id,
            relation.target_literal,
        )

    merged = {key(item): item for item in existing}
    merged.update({key(item): item for item in incoming})
    return [merged[current_key] for current_key in sorted(merged)]


def _merge_review_items(
    existing: list[CompilerReviewItem],
    incoming: list[CompilerReviewItem],
) -> list[CompilerReviewItem]:
    def key(item: CompilerReviewItem) -> tuple[str, str, str]:
        return item.review_type, item.title, item.body

    merged = {key(item): item for item in existing}
    merged.update({key(item): item for item in incoming})
    return [merged[current_key] for current_key in sorted(merged)]
