from backend.app.domain.query import EvidenceCandidate, EvidenceRankingResult, QueryPlan
from backend.app.services.query_contracts import QueryLLMClient


class EvidenceRanker:
    def __init__(self, llm_client: QueryLLMClient) -> None:
        self.llm_client = llm_client

    async def rank(
        self,
        question: str,
        plan: QueryPlan,
        candidates: list[EvidenceCandidate],
        max_evidence: int,
    ) -> EvidenceRankingResult:
        if not candidates:
            return EvidenceRankingResult(
                selected_evidence_ids=[],
                rejected_evidence_ids=[],
                assessments=[],
                contradictions=[],
                missing_evidence=["Không truy xuất được bằng chứng phù hợp."],
                reasoning_summary="SQLite FTS không trả về candidate nào.",
            )

        ranking = await self.llm_client.rank_evidence(question, plan, candidates, max_evidence)
        valid_ids = {candidate.evidence_id for candidate in candidates}
        selected_ids = [
            evidence_id
            for evidence_id in ranking.selected_evidence_ids
            if evidence_id in valid_ids
        ][:max_evidence]
        rejected_ids = [
            evidence_id
            for evidence_id in ranking.rejected_evidence_ids
            if evidence_id in valid_ids and evidence_id not in selected_ids
        ]
        rejected_ids.extend(
            candidate.evidence_id
            for candidate in candidates
            if candidate.evidence_id not in selected_ids
            and candidate.evidence_id not in rejected_ids
        )
        assessments = [
            assessment
            for assessment in ranking.assessments
            if assessment.evidence_id in valid_ids
        ]
        return EvidenceRankingResult(
            selected_evidence_ids=selected_ids,
            rejected_evidence_ids=list(dict.fromkeys(rejected_ids)),
            assessments=assessments,
            contradictions=ranking.contradictions,
            missing_evidence=ranking.missing_evidence,
            reasoning_summary=ranking.reasoning_summary,
        )
