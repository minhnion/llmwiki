from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import query_run_id
from backend.app.domain.query import (
    EvidenceCandidate,
    EvidenceRankingResult,
    QueryAskCommand,
    QueryResult,
    QuerySynthesisResult,
)
from backend.app.repositories.query import SQLiteQueryRepository
from backend.app.services.answer_synthesizer import AnswerSynthesizer
from backend.app.services.evidence_ranker import EvidenceRanker
from backend.app.services.query_planner import QueryPlanner
from backend.app.services.wiki_log import WikiLogWriter


class QueryEngine:
    def __init__(
        self,
        repository: SQLiteQueryRepository,
        planner: QueryPlanner,
        ranker: EvidenceRanker,
        synthesizer: AnswerSynthesizer,
        wiki_log_writer: WikiLogWriter,
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.ranker = ranker
        self.synthesizer = synthesizer
        self.wiki_log_writer = wiki_log_writer

    async def ask(self, command: QueryAskCommand) -> QueryResult:
        normalized_command = QueryAskCommand.model_validate(command.model_dump())
        normalized_question = normalized_command.question.strip()
        if not normalized_question:
            raise ValueError("Question must not be blank.")
        normalized_command.question = normalized_question

        created_at = utc_now_iso()
        plan = await self.planner.plan(normalized_command)
        candidates = self.repository.search_evidence(
            question=normalized_question,
            plan=plan,
            source_ids=normalized_command.source_ids,
            tags=normalized_command.tags,
            max_candidates=normalized_command.max_candidates,
        )
        ranking = await self.ranker.rank(
            question=normalized_question,
            plan=plan,
            candidates=candidates,
            max_evidence=normalized_command.max_evidence,
        )
        selected_evidence = _select_evidence(candidates, ranking.selected_evidence_ids)

        if selected_evidence:
            synthesis = await self.synthesizer.synthesize(
                question=normalized_question,
                plan=plan,
                evidence=selected_evidence,
                ranking=ranking,
            )
        else:
            synthesis = _insufficient_synthesis(ranking)

        result = QueryResult(
            query_id=query_run_id(),
            question=normalized_question,
            mode=normalized_command.mode,
            plan=plan,
            answer=synthesis.answer,
            confidence=synthesis.confidence,
            citations=synthesis.citations,
            used_claim_ids=synthesis.used_claim_ids,
            matched_entities=synthesis.matched_entities,
            contradictions=synthesis.contradictions,
            open_questions=synthesis.open_questions,
            follow_up_questions=synthesis.follow_up_questions,
            selected_evidence=selected_evidence,
            candidate_count=len(candidates),
            created_at=created_at,
        )
        self.repository.save_query_result(result, ranking)
        self.wiki_log_writer.append_query_answered(
            timestamp=created_at,
            query_id=result.query_id,
            question=normalized_question,
            confidence=result.confidence,
            citation_count=len(result.citations),
        )
        return result


def _select_evidence(
    candidates: list[EvidenceCandidate],
    selected_ids: list[str],
) -> list[EvidenceCandidate]:
    candidates_by_id = {candidate.evidence_id: candidate for candidate in candidates}
    return [
        candidates_by_id[evidence_id]
        for evidence_id in selected_ids
        if evidence_id in candidates_by_id
    ]


def _insufficient_synthesis(ranking: EvidenceRankingResult) -> QuerySynthesisResult:
    open_questions = ranking.missing_evidence or [
        "Ingest more relevant source material or broaden the query filters."
    ]
    return QuerySynthesisResult(
        answer=(
            "I do not have enough source-grounded evidence in the current LLM Wiki "
            "to answer this question reliably."
        ),
        confidence="insufficient",
        citations=[],
        used_claim_ids=[],
        matched_entities=[],
        contradictions=ranking.contradictions,
        open_questions=open_questions,
        follow_up_questions=[],
    )
