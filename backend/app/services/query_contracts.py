from typing import Protocol

from backend.app.domain.query import (
    EvidenceCandidate,
    EvidenceRankingResult,
    QueryAskCommand,
    QueryPlan,
    QuerySynthesisResult,
)


class QueryLLMClient(Protocol):
    async def plan_query(self, command: QueryAskCommand) -> QueryPlan:
        """Create a structured retrieval plan from a natural-language question."""

    async def rank_evidence(
        self,
        question: str,
        plan: QueryPlan,
        candidates: list[EvidenceCandidate],
        max_evidence: int,
    ) -> EvidenceRankingResult:
        """Judge and rerank candidate evidence for the question."""

    async def synthesize_answer(
        self,
        question: str,
        plan: QueryPlan,
        evidence: list[EvidenceCandidate],
        ranking: EvidenceRankingResult,
    ) -> QuerySynthesisResult:
        """Synthesize a grounded answer from selected evidence."""
