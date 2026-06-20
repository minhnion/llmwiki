from backend.app.domain.agent import (
    AgentAnswer,
    AnswerCitation,
    EvidenceDraft,
    PageChange,
    QueryPlan,
    ReviewDraft,
    SourceAnalysis,
    WikiChangeSet,
)
from backend.app.services.llm_client import LLMUsage


class FakeWikiAgentLLM:
    def __init__(self) -> None:
        self.source_id = ""

    async def analyze_source(self, source, purpose, schema, catalog):
        self.source_id = source.id
        return (
            SourceAnalysis(
                summary="The source explains persistent wiki knowledge.",
                relevant_page_ids=[],
                wiki_search_queries=["persistent wiki"],
                possible_conflicts=[],
                uncertainties=[],
            ),
            _usage(),
        )

    async def propose_wiki_changes(
        self,
        source,
        purpose,
        schema,
        analysis,
        relevant_pages,
    ):
        return (
            WikiChangeSet(
                changes=[
                    PageChange(
                        action="create",
                        page_id=None,
                        path="sources/wiki-source.md",
                        title="Wiki Source",
                        page_type="source summary",
                        summary="Summary of the source.",
                        body="# Wiki Source\n\nSee [[pages/persistent-wiki.md|Persistent Wiki]].",
                        status="active",
                        confidence=0.95,
                        evidence=[
                            EvidenceDraft(
                                source_id=source.id,
                                locator="paragraph 1",
                                quote_or_summary="A persistent wiki accumulates knowledge.",
                                modality="text",
                                confidence=0.95,
                            )
                        ],
                        related_page_ids=[],
                    ),
                    PageChange(
                        action="create",
                        page_id=None,
                        path="pages/persistent-wiki.md",
                        title="Persistent Wiki",
                        page_type="knowledge pattern",
                        summary="Knowledge is maintained before query time.",
                        body="# Persistent Wiki\n\nKnowledge compounds across operations.",
                        status="active",
                        confidence=0.93,
                        evidence=[
                            EvidenceDraft(
                                source_id=source.id,
                                locator="paragraph 1",
                                quote_or_summary="A persistent wiki accumulates knowledge.",
                                modality="text",
                                confidence=0.95,
                            )
                        ],
                        related_page_ids=[],
                    ),
                ],
                reviews=[
                    ReviewDraft(
                        review_type="follow_up",
                        title="Evaluate compounding",
                        body="Add more sources to evaluate cross-source updates.",
                        severity="low",
                        source_id=source.id,
                        page_id=None,
                    )
                ],
                overview_body="The wiki currently covers the persistent wiki pattern.",
                notes=[],
            ),
            _usage(),
        )

    async def plan_query(
        self,
        question,
        mode,
        purpose,
        overview,
        index,
        catalog,
        sources,
    ):
        return (
            QueryPlan(
                search_queries=["persistent wiki knowledge"],
                page_ids=[catalog[0].id],
                source_ids_to_inspect=[],
                answer_language="English",
                notes=[],
            ),
            _usage(),
        )

    async def answer_query(self, question, mode, plan, pages, sources):
        page = pages[0]
        evidence = page.evidence_refs[0]
        return (
            AgentAnswer(
                answer="A persistent wiki stores maintained knowledge before query time.",
                confidence="high",
                citations=[
                    AnswerCitation(
                        page_id=page.id,
                        source_id=evidence.source_id,
                        locator=evidence.locator,
                        quote_or_summary=evidence.quote_or_summary,
                    )
                ],
                open_questions=[],
                reusable_summary=None,
            ),
            _usage(),
        )


def _usage() -> LLMUsage:
    return LLMUsage(
        model="fake-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=10,
    )
