from backend.app.domain.compiler import CompilationBundle, SourceManifest
from backend.app.domain.extraction import (
    ExtractedClaim,
    ExtractedEntity,
    ExtractedEvidence,
    ExtractedReviewItem,
    IngestExtractionResult,
)
from backend.app.domain.models import SourceRef


class ArtifactProjector:
    """Projects Compiler V2 artifacts into the legacy query/graph read model."""

    def project(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        bundle: CompilationBundle,
    ) -> IngestExtractionResult:
        locator_by_evidence = {
            evidence.local_id: _render_locator(evidence.locator.kind, evidence.locator.value)
            for evidence in bundle.evidence_items
        }
        claims = [
            ExtractedClaim(
                text=statement.text,
                subject=statement.subject,
                predicate=statement.predicate,
                object=statement.object,
                evidence_locators=[
                    locator_by_evidence[local_id]
                    for local_id in statement.evidence_local_ids
                ],
                evidence_local_ids=statement.evidence_local_ids,
                confidence=statement.confidence,
                status=statement.status,
            )
            for artifact in bundle.artifacts
            for statement in artifact.statements
        ]
        entities = [
            ExtractedEntity(
                name=artifact.title,
                entity_type=artifact.artifact_type,
                aliases=artifact.aliases,
                description=artifact.summary,
                evidence_locators=[
                    locator_by_evidence[local_id]
                    for local_id in artifact.evidence_local_ids
                ],
                evidence_local_ids=artifact.evidence_local_ids,
                confidence=artifact.confidence,
            )
            for artifact in bundle.artifacts
        ]
        return IngestExtractionResult(
            source_title=source.title,
            source_summary=manifest.document_profile.summary,
            source_language=manifest.language,
            document_type=manifest.document_profile.kind,
            key_takeaways=[
                artifact.summary
                for artifact in sorted(
                    bundle.artifacts,
                    key=lambda item: item.confidence,
                    reverse=True,
                )[:8]
            ],
            evidence_items=[
                ExtractedEvidence(
                    local_id=evidence.local_id,
                    locator=_render_locator(
                        evidence.locator.kind,
                        evidence.locator.value,
                    ),
                    modality=evidence.modality,
                    text=evidence.content,
                    summary=evidence.summary,
                    confidence=evidence.confidence,
                )
                for evidence in bundle.evidence_items
            ],
            claims=claims,
            entities=entities,
            review_items=[
                ExtractedReviewItem(
                    review_type=item.review_type,
                    title=item.title,
                    body=item.body,
                    severity=item.severity,
                    evidence_locators=[
                        locator_by_evidence[local_id]
                        for local_id in item.evidence_local_ids
                    ],
                    evidence_local_ids=item.evidence_local_ids,
                )
                for item in bundle.review_items
            ],
            open_questions=[
                gap
                for gap in bundle.notes
                if gap.strip()
            ],
        )


def _render_locator(kind: str, value: str) -> str:
    return f"{kind}: {value}" if kind.strip() else value
