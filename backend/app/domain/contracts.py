from typing import Protocol

from backend.app.domain.agent import (
    AgentAnswer,
    QueryPlan,
    SourceAnalysis,
    WikiChangeSet,
)
from backend.app.domain.models import SourceRef, WikiPage, WikiPageSummary


class WikiAgentLLM(Protocol):
    async def analyze_source(
        self,
        source: SourceRef,
        purpose: str,
        schema: str,
        catalog: list[WikiPageSummary],
    ) -> tuple[SourceAnalysis, "LLMUsage"]:
        """Understand a source and request relevant wiki searches."""

    async def propose_wiki_changes(
        self,
        source: SourceRef,
        purpose: str,
        schema: str,
        analysis: SourceAnalysis,
        relevant_pages: list[WikiPage],
    ) -> tuple[WikiChangeSet, "LLMUsage"]:
        """Create a source-grounded multi-page wiki change set."""

    async def plan_query(
        self,
        question: str,
        mode: str,
        purpose: str,
        overview: str,
        index: str,
        catalog: list[WikiPageSummary],
        sources: list[SourceRef],
    ) -> tuple[QueryPlan, "LLMUsage"]:
        """Request wiki searches and optional source verification."""

    async def answer_query(
        self,
        question: str,
        mode: str,
        plan: QueryPlan,
        pages: list[WikiPage],
        sources: list[SourceRef],
    ) -> tuple[AgentAnswer, "LLMUsage"]:
        """Answer from selected wiki pages and optional raw source files."""


class LLMUsage(Protocol):
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
