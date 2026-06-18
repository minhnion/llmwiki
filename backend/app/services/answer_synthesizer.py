from backend.app.domain.query import (
    EvidenceCandidate,
    EvidenceRankingResult,
    QueryPlan,
    QuerySynthesisResult,
)
from backend.app.services.query_contracts import QueryLLMClient


class AnswerSynthesizer:
    def __init__(self, llm_client: QueryLLMClient) -> None:
        self.llm_client = llm_client

    async def synthesize(
        self,
        question: str,
        plan: QueryPlan,
        evidence: list[EvidenceCandidate],
        ranking: EvidenceRankingResult,
    ) -> QuerySynthesisResult:
        synthesis = await self.llm_client.synthesize_answer(question, plan, evidence, ranking)
        return self._ground_citations(synthesis, evidence)

    @staticmethod
    def _ground_citations(
        synthesis: QuerySynthesisResult,
        evidence: list[EvidenceCandidate],
    ) -> QuerySynthesisResult:
        evidence_by_id = {candidate.evidence_id: candidate for candidate in evidence}
        citations = [
            citation
            for citation in synthesis.citations
            if citation.evidence_id in evidence_by_id
        ]
        selected_claim_ids = {
            claim_id
            for candidate in evidence
            for claim_id in candidate.claim_ids
        }
        confidence = synthesis.confidence
        if confidence == "high" and (not citations or ranking_has_material_gap(synthesis)):
            confidence = "low"
        return QuerySynthesisResult(
            answer=synthesis.answer,
            confidence=confidence,
            citations=citations,
            used_claim_ids=[
                claim_id
                for claim_id in synthesis.used_claim_ids
                if claim_id in selected_claim_ids
            ],
            matched_entities=synthesis.matched_entities,
            contradictions=synthesis.contradictions,
            open_questions=synthesis.open_questions,
            follow_up_questions=synthesis.follow_up_questions,
        )


def ranking_has_material_gap(synthesis: QuerySynthesisResult) -> bool:
    return bool(synthesis.open_questions) and not synthesis.used_claim_ids
