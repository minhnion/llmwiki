from collections import defaultdict

from backend.app.domain.graph import (
    ClaimGraphContext,
    ContradictionDetectionResult,
    ExtractedContradiction,
)
from backend.app.services.graph_contracts import GraphLLMClient


class ContradictionDetector:
    def __init__(self, llm_client: GraphLLMClient) -> None:
        self.llm_client = llm_client

    async def detect(
        self,
        claims: list[ClaimGraphContext],
        max_claims_per_group: int = 40,
    ) -> ContradictionDetectionResult:
        contradictions: list[ExtractedContradiction] = []
        notes: list[str] = []
        seen: set[tuple[str, str, str]] = set()

        for group in _candidate_groups(claims, max_claims_per_group):
            result = await self.llm_client.detect_contradictions(group)
            notes.extend(result.notes)
            for contradiction in result.contradictions:
                key = tuple(
                    [
                        *sorted([contradiction.claim_a_id, contradiction.claim_b_id]),
                        contradiction.relationship,
                    ]
                )
                if key in seen:
                    continue
                seen.add(key)
                contradictions.append(contradiction)

        return ContradictionDetectionResult(contradictions=contradictions, notes=notes)


def _candidate_groups(
    claims: list[ClaimGraphContext],
    max_claims_per_group: int,
) -> list[list[ClaimGraphContext]]:
    groups_by_subject: dict[str, list[ClaimGraphContext]] = defaultdict(list)
    for claim in claims:
        subject_key = claim.subject.strip().lower()
        if subject_key:
            groups_by_subject[subject_key].append(claim)

    groups: list[list[ClaimGraphContext]] = []
    for group in groups_by_subject.values():
        if len(group) < 2:
            continue
        for start in range(0, len(group), max_claims_per_group):
            chunk = group[start : start + max_claims_per_group]
            if len(chunk) >= 2:
                groups.append(chunk)
    return groups
