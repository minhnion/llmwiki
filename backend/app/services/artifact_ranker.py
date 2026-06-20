from backend.app.domain.query import (
    ArtifactAssessment,
    ArtifactCandidate,
    ArtifactRankingResult,
    QueryPlan,
)
from backend.app.services.query_contracts import QueryLLMClient


class ArtifactRanker:
    def __init__(self, llm_client: QueryLLMClient) -> None:
        self.llm_client = llm_client

    async def rank(
        self,
        question: str,
        plan: QueryPlan,
        candidates: list[ArtifactCandidate],
        max_artifacts: int,
        max_evidence: int,
    ) -> ArtifactRankingResult:
        if not candidates:
            return ArtifactRankingResult(
                selected_artifact_ids=[],
                rejected_artifact_ids=[],
                selected_evidence_ids=[],
                assessments=[],
                contradictions=[],
                missing_knowledge=["Không truy xuất được artifact phù hợp."],
                reasoning_summary="Semantic artifact retrieval did not return candidates.",
            )

        ranking = await self.llm_client.rank_artifacts(
            question=question,
            plan=plan,
            candidates=candidates,
            max_artifacts=max_artifacts,
            max_evidence=max_evidence,
        )
        valid_artifact_ids = {candidate.artifact_id for candidate in candidates}
        selected_artifact_ids = [
            artifact_id
            for artifact_id in ranking.selected_artifact_ids
            if artifact_id in valid_artifact_ids
        ][:max_artifacts]
        selected_artifact_set = set(selected_artifact_ids)
        valid_selected_evidence_ids = {
            evidence.evidence_id
            for candidate in candidates
            if candidate.artifact_id in selected_artifact_set
            for evidence in candidate.evidence
        }

        evidence_ids_from_assessments = [
            evidence_id
            for assessment in ranking.assessments
            if assessment.artifact_id in selected_artifact_set
            for evidence_id in assessment.selected_evidence_ids
        ]
        selected_evidence_ids = [
            evidence_id
            for evidence_id in [
                *ranking.selected_evidence_ids,
                *evidence_ids_from_assessments,
            ]
            if evidence_id in valid_selected_evidence_ids
        ][:max_evidence]

        rejected_artifact_ids = [
            artifact_id
            for artifact_id in ranking.rejected_artifact_ids
            if artifact_id in valid_artifact_ids and artifact_id not in selected_artifact_set
        ]
        rejected_artifact_ids.extend(
            candidate.artifact_id
            for candidate in candidates
            if candidate.artifact_id not in selected_artifact_set
            and candidate.artifact_id not in rejected_artifact_ids
        )

        assessments = [
            ArtifactAssessment(
                artifact_id=assessment.artifact_id,
                relevance=assessment.relevance,
                support_type=assessment.support_type,
                selected_evidence_ids=[
                    evidence_id
                    for evidence_id in assessment.selected_evidence_ids
                    if evidence_id in valid_selected_evidence_ids
                ],
                reason=assessment.reason,
                confidence=assessment.confidence,
            )
            for assessment in ranking.assessments
            if assessment.artifact_id in valid_artifact_ids
        ]
        return ArtifactRankingResult(
            selected_artifact_ids=list(dict.fromkeys(selected_artifact_ids)),
            rejected_artifact_ids=list(dict.fromkeys(rejected_artifact_ids)),
            selected_evidence_ids=list(dict.fromkeys(selected_evidence_ids)),
            assessments=assessments,
            contradictions=ranking.contradictions,
            missing_knowledge=ranking.missing_knowledge,
            reasoning_summary=ranking.reasoning_summary,
        )
