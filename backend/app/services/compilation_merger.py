from backend.app.domain.compiler import (
    CompilationBundle,
    CompilationPassResult,
    CompiledArtifact,
    CompiledEvidence,
    CompiledRelation,
    CompiledSemanticNode,
    CompilerReviewItem,
)


class CompilationMerger:
    def merge(
        self,
        current: CompilationBundle,
        incoming: CompilationPassResult,
    ) -> CompilationBundle:
        evidence = _merge_by_local_id(current.evidence_items, incoming.evidence_items)
        artifacts = _merge_artifacts(current.artifacts, incoming.artifacts)
        semantic_nodes = _merge_semantic_nodes(
            current.semantic_nodes,
            incoming.semantic_nodes,
        )
        relations = _merge_relations(current.relations, incoming.relations)
        review_items = _merge_review_items(current.review_items, incoming.review_items)
        merged = CompilationBundle(
            evidence_items=evidence,
            artifacts=artifacts,
            semantic_nodes=semantic_nodes,
            relations=relations,
            review_items=review_items,
            covered_unit_ids=[],
            notes=list(dict.fromkeys([*current.notes, *incoming.notes])),
        )
        return merged.model_copy(update={"covered_unit_ids": _supported_unit_ids(merged)})

    @staticmethod
    def empty() -> CompilationBundle:
        return CompilationBundle(
            evidence_items=[],
            artifacts=[],
            semantic_nodes=[],
            relations=[],
            review_items=[],
            covered_unit_ids=[],
            notes=[],
        )


def _merge_by_local_id(
    existing: list[CompiledEvidence],
    incoming: list[CompiledEvidence],
) -> list:
    merged = {item.local_id: item for item in existing}
    merged.update({item.local_id: item for item in incoming})
    return [merged[key] for key in sorted(merged)]


def _merge_artifacts(
    existing: list[CompiledArtifact],
    incoming: list[CompiledArtifact],
) -> list[CompiledArtifact]:
    merged = {item.local_id: item for item in existing}
    for item in incoming:
        previous = merged.get(item.local_id)
        if previous is None:
            merged[item.local_id] = item
            continue
        statements = {statement.local_id: statement for statement in previous.statements}
        statements.update({statement.local_id: statement for statement in item.statements})
        merged[item.local_id] = item.model_copy(
            update={
                "summary": _merge_text(previous.summary, item.summary),
                "content": _merge_text(previous.content, item.content),
                "aliases": _dedupe([*previous.aliases, *item.aliases]),
                "scope": _merge_metadata(previous.scope, item.scope),
                "evidence_local_ids": _dedupe(
                    [*previous.evidence_local_ids, *item.evidence_local_ids]
                ),
                "source_unit_ids": _dedupe(
                    [*previous.source_unit_ids, *item.source_unit_ids]
                ),
                "related_artifact_local_ids": _dedupe(
                    [
                        *previous.related_artifact_local_ids,
                        *item.related_artifact_local_ids,
                    ]
                ),
                "statements": [
                    statements[key] for key in sorted(statements)
                ],
                "confidence": max(previous.confidence, item.confidence),
                "review_status": "unreviewed",
                "metadata": _merge_metadata(previous.metadata, item.metadata),
            }
        )
    return [merged[key] for key in sorted(merged)]


def _merge_semantic_nodes(
    existing: list[CompiledSemanticNode],
    incoming: list[CompiledSemanticNode],
) -> list[CompiledSemanticNode]:
    merged = {item.local_id: item for item in existing}
    for item in incoming:
        previous = merged.get(item.local_id)
        if previous is None:
            merged[item.local_id] = item
            continue
        merged[item.local_id] = item.model_copy(
            update={
                "aliases": _dedupe([*previous.aliases, *item.aliases]),
                "description": _merge_text(
                    previous.description,
                    item.description,
                ),
                "evidence_local_ids": _dedupe(
                    [*previous.evidence_local_ids, *item.evidence_local_ids]
                ),
                "source_unit_ids": _dedupe(
                    [*previous.source_unit_ids, *item.source_unit_ids]
                ),
                "confidence": max(previous.confidence, item.confidence),
            }
        )
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


def _supported_unit_ids(bundle: CompilationBundle) -> list[str]:
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
    return sorted(evidence_units & artifact_units & statement_units)


def _merge_review_items(
    existing: list[CompilerReviewItem],
    incoming: list[CompilerReviewItem],
) -> list[CompilerReviewItem]:
    def key(item: CompilerReviewItem) -> tuple[str, str, str]:
        return item.review_type, item.title, item.body

    merged = {key(item): item for item in existing}
    merged.update({key(item): item for item in incoming})
    return [merged[current_key] for current_key in sorted(merged)]


def _merge_text(existing: str, incoming: str) -> str:
    existing = existing.strip()
    incoming = incoming.strip()
    if not existing:
        return incoming
    if not incoming or incoming in existing:
        return existing
    if existing in incoming:
        return incoming
    return f"{existing}\n\n{incoming}"


def _merge_metadata(existing: list, incoming: list) -> list:
    merged = {(item.key, item.value): item for item in existing}
    merged.update({(item.key, item.value): item for item in incoming})
    return [merged[key] for key in sorted(merged)]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
