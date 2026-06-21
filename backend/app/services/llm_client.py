import asyncio
import base64
import json
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from backend.app.domain.agent import (
    AgentAnswer,
    QueryPlan,
    SourceAnalysis,
    WikiChangeSet,
)
from backend.app.domain.models import SourceRef, WikiPage, WikiPageSummary

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


@dataclass(frozen=True)
class LLMUsage:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class OpenAIWikiAgentClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_output_tokens: int,
        preferred_language: str,
    ) -> None:
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.preferred_language = preferred_language
        self.client = OpenAI(api_key=api_key)

    async def analyze_source(
        self,
        source: SourceRef,
        purpose: str,
        schema: str,
        catalog: list[WikiPageSummary],
    ) -> tuple[SourceAnalysis, LLMUsage]:
        prompt = {
            "source": _source_metadata(source),
            "wiki_purpose": purpose,
            "wiki_schema": schema,
            "current_wiki_catalog": [item.model_dump() for item in catalog],
        }
        return await self._structured(
            SourceAnalysis,
            "wiki_agent_source_analysis",
            _understand_instructions(self.preferred_language),
            [_file_message(source.path, prompt)],
        )

    async def propose_wiki_changes(
        self,
        source: SourceRef,
        purpose: str,
        schema: str,
        analysis: SourceAnalysis,
        relevant_pages: list[WikiPage],
    ) -> tuple[WikiChangeSet, LLMUsage]:
        prompt = {
            "source": _source_metadata(source),
            "wiki_purpose": purpose,
            "wiki_schema": schema,
            "source_analysis": analysis.model_dump(),
            "relevant_existing_pages": [_page_payload(page) for page in relevant_pages],
        }
        return await self._structured(
            WikiChangeSet,
            "wiki_agent_change_set",
            _maintain_instructions(self.preferred_language),
            [_file_message(source.path, prompt)],
        )

    async def plan_query(
        self,
        question: str,
        mode: str,
        purpose: str,
        overview: str,
        index: str,
        catalog: list[WikiPageSummary],
        sources: list[SourceRef],
    ) -> tuple[QueryPlan, LLMUsage]:
        return await self._structured(
            QueryPlan,
            "wiki_agent_query_plan",
            _query_plan_instructions(self.preferred_language),
            [
                _text_message(
                    {
                        "question": question,
                        "mode": mode,
                        "wiki_purpose": purpose,
                        "wiki_overview": overview,
                        "wiki_index": index,
                        "wiki_catalog": [item.model_dump() for item in catalog],
                        "source_catalog": [_source_metadata(source) for source in sources],
                    }
                )
            ],
        )

    async def answer_query(
        self,
        question: str,
        mode: str,
        plan: QueryPlan,
        pages: list[WikiPage],
        sources: list[SourceRef],
    ) -> tuple[AgentAnswer, LLMUsage]:
        content: list[dict[str, object]] = []
        for source in sources:
            content.append(_file_content(source.path))
        content.append(
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "question": question,
                        "mode": mode,
                        "plan": plan.model_dump(),
                        "wiki_pages": [_page_payload(page) for page in pages],
                        "inspected_sources": [_source_metadata(source) for source in sources],
                    },
                    ensure_ascii=False,
                ),
            }
        )
        return await self._structured(
            AgentAnswer,
            "wiki_agent_answer",
            _answer_instructions(self.preferred_language),
            [{"role": "user", "content": content}],
        )

    async def _structured(
        self,
        output_model: type[StructuredModel],
        name: str,
        instructions: str,
        inputs: list[dict[str, object]],
    ) -> tuple[StructuredModel, LLMUsage]:
        started = time.perf_counter()
        response = await asyncio.to_thread(
            self.client.responses.create,
            model=self.model,
            instructions=instructions,
            input=inputs,
            text={
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "schema": output_model.model_json_schema(),
                    "strict": True,
                }
            },
            max_output_tokens=self.max_output_tokens,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage", None)
        return (
            output_model.model_validate_json(response.output_text),
            LLMUsage(
                model=self.model,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                latency_ms=elapsed_ms,
            ),
        )


def _understand_instructions(preferred_language: str) -> str:
    return (
        "You are the understanding phase of a general-purpose Wiki Agent. Read the entire "
        "raw source using text, visual, table, and layout information available to the model. "
        "Use purpose.md for direction and schema.md for operating rules. Decide meaning "
        "yourself; do not assume a domain taxonomy, fixed page types, keyword router, or "
        "document structure. Compare the source with the current wiki catalog. Return a concise "
        "decision brief, exact relevant_page_ids from the catalog, and semantic wiki search "
        "queries needed before editing. Identify "
        "possible support, qualification, contradiction, duplication, and uncertainty. Do not "
        "write wiki pages yet and do not expose private chain-of-thought. Preserve the source "
        f"language; when unclear use {preferred_language}. Return only schema-valid JSON."
    )


def _maintain_instructions(preferred_language: str) -> str:
    return (
        "You are the maintenance phase of a general-purpose Wiki Agent. Integrate the raw "
        "source into the existing Markdown wiki. Create, update, link, qualify, contradict, or "
        "request review based on meaning. Prefer updating an existing semantic page over "
        "creating a duplicate. Page type is an open string. Generated paths must be under "
        "sources/, pages/, or queries/ and end in .md. For updates and deletes use the exact "
        "existing page_id. Body is Markdown without YAML frontmatter; the backend renders "
        "frontmatter. Use [[relative/path.md|label]] wikilinks only when the target exists in "
        "the supplied pages or is created in this same change set. Every factual addition must "
        "include source evidence with a verifiable locator and faithful quote or summary. "
        "Preserve useful existing knowledge and provenance. Never invent facts or identifiers. "
        "A source summary page should be created or updated for the current source. Put "
        "ambiguous identity, merge, or contradiction decisions into reviews. Do not use a "
        "fixed ontology or optimize for one document. Preserve source language; when unclear "
        f"use {preferred_language}. Return only schema-valid JSON."
    )


def _query_plan_instructions(preferred_language: str) -> str:
    return (
        "You are the planning step of a Wiki Agent query. Use purpose, overview, and index to "
        "select exact relevant page IDs from the supplied catalog and request a small set of "
        "semantic wiki searches. Request only supplied source IDs, and only when raw "
        "verification is likely necessary. "
        "Do not answer yet. fast/deep/audit controls effort and verification, not domain "
        "routing. Do not use a fixed intent taxonomy. Keep searches in the question/source "
        f"language; when unclear use {preferred_language}. Return only schema-valid JSON."
    )


def _answer_instructions(preferred_language: str) -> str:
    return (
        "You are a general-purpose Wiki Agent answering from supplied full wiki pages and "
        "optional raw source files. Synthesize directly and faithfully. Cite only supplied "
        "page_id/source_id combinations and locators that support the claim. Distinguish "
        "absence from incomplete retrieval. Surface relevant qualification, contradiction, "
        "and uncertainty. If evidence is insufficient, say so. reusable_summary is optional "
        "and should contain only knowledge worth saving back into the wiki. Answer in the "
        f"user's language; when unclear use {preferred_language}. Return only schema-valid JSON."
    )


def _source_metadata(source: SourceRef) -> dict[str, object]:
    return {
        "id": source.id,
        "title": source.title,
        "source_type": source.source_type,
        "sha256": source.sha256,
        "path": str(source.path),
    }


def _page_payload(page: WikiPage) -> dict[str, object]:
    return {
        "id": page.id,
        "path": str(page.path),
        "title": page.title,
        "type": page.page_type,
        "summary": page.summary,
        "body": page.body,
        "status": page.status,
        "confidence": page.confidence,
        "evidence": [item.model_dump() for item in page.evidence_refs],
        "related_page_ids": page.related_page_ids,
    }


def _text_message(payload: dict[str, object]) -> dict[str, object]:
    return {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": json.dumps(payload, ensure_ascii=False),
            }
        ],
    }


def _file_message(path: Path, payload: dict[str, object]) -> dict[str, object]:
    return {
        "role": "user",
        "content": [
            _file_content(path),
            {
                "type": "input_text",
                "text": json.dumps(payload, ensure_ascii=False),
            },
        ],
    }


def _file_content(path: Path) -> dict[str, object]:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "input_file",
        "filename": path.name,
        "file_data": f"data:{mime};base64,{encoded}",
    }
