import asyncio
import base64
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from backend.app.core.text import compact_text
from backend.app.domain.extraction import (
    INGEST_EXTRACTION_JSON_SCHEMA,
    IngestExtractionResult,
)
from backend.app.domain.models import SourceRef
from backend.app.domain.query import (
    EVIDENCE_RANKING_JSON_SCHEMA,
    QUERY_PLAN_JSON_SCHEMA,
    QUERY_SYNTHESIS_JSON_SCHEMA,
    EvidenceCandidate,
    EvidenceRankingResult,
    QueryAskCommand,
    QueryPlan,
    QuerySynthesisResult,
)


@dataclass(frozen=True)
class LLMRequest:
    instructions: str
    inputs: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    structured: dict[str, object] | None = None


class LLMClient(Protocol):
    async def create_response(self, request: LLMRequest) -> LLMResponse:
        """Create a model response for an application workflow."""

    async def extract_source(self, source: SourceRef) -> IngestExtractionResult:
        """Extract wiki-ready knowledge from a source file."""


class OpenAIResponsesClient:
    """Adapter for OpenAI Responses API file and structured-output calls."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_output_tokens: int = 6000,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.client = OpenAI(api_key=api_key)

    async def create_response(self, request: LLMRequest) -> LLMResponse:
        response = await asyncio.to_thread(
            self.client.responses.create,
            model=self.model,
            instructions=request.instructions,
            input=request.inputs,
            max_output_tokens=self.max_output_tokens,
        )
        return LLMResponse(text=response.output_text)

    async def extract_source(self, source: SourceRef) -> IngestExtractionResult:
        file_data = _base64_file_data(source.path, source.mime_type)
        payload = await self._create_structured_response(
            name="llm_wiki_ingest_extraction",
            schema=INGEST_EXTRACTION_JSON_SCHEMA,
            instructions=_ingest_instructions(),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": source.path.name,
                            "file_data": file_data,
                        },
                        {
                            "type": "input_text",
                            "text": _source_prompt(source),
                        },
                    ],
                }
            ],
        )
        return IngestExtractionResult.model_validate(payload)

    async def plan_query(self, command: QueryAskCommand) -> QueryPlan:
        payload = await self._create_structured_response(
            name="llm_wiki_query_plan",
            schema=QUERY_PLAN_JSON_SCHEMA,
            instructions=_query_plan_instructions(),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(command.model_dump(), ensure_ascii=False),
                        }
                    ],
                }
            ],
        )
        return QueryPlan.model_validate(payload)

    async def rank_evidence(
        self,
        question: str,
        plan: QueryPlan,
        candidates: list[EvidenceCandidate],
        max_evidence: int,
    ) -> EvidenceRankingResult:
        payload = await self._create_structured_response(
            name="llm_wiki_evidence_ranking",
            schema=EVIDENCE_RANKING_JSON_SCHEMA,
            instructions=_evidence_ranking_instructions(max_evidence),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "question": question,
                                    "plan": plan.model_dump(),
                                    "max_evidence": max_evidence,
                                    "candidates": [
                                        _candidate_payload(candidate)
                                        for candidate in candidates
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return EvidenceRankingResult.model_validate(payload)

    async def synthesize_answer(
        self,
        question: str,
        plan: QueryPlan,
        evidence: list[EvidenceCandidate],
        ranking: EvidenceRankingResult,
    ) -> QuerySynthesisResult:
        payload = await self._create_structured_response(
            name="llm_wiki_query_synthesis",
            schema=QUERY_SYNTHESIS_JSON_SCHEMA,
            instructions=_query_synthesis_instructions(),
            inputs=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "question": question,
                                    "plan": plan.model_dump(),
                                    "ranking": ranking.model_dump(),
                                    "selected_evidence": [
                                        _candidate_payload(candidate)
                                        for candidate in evidence
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        )
        return QuerySynthesisResult.model_validate(payload)

    async def _create_structured_response(
        self,
        name: str,
        schema: dict[str, object],
        instructions: str,
        inputs: list[dict[str, object]],
    ) -> dict[str, object]:
        response = await asyncio.to_thread(
            self.client.responses.create,
            model=self.model,
            instructions=instructions,
            input=inputs,
            text={
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "schema": schema,
                    "strict": True,
                }
            },
            max_output_tokens=self.max_output_tokens,
        )
        return json.loads(response.output_text)


def _base64_file_data(path: Path, mime_type: str | None) -> str:
    guessed_mime = mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{guessed_mime};base64,{encoded}"


def _ingest_instructions() -> str:
    return (
        "You are the ingest engine for a general-purpose LLM Wiki. "
        "Read the provided file directly, including visual/page information when available. "
        "Extract source-grounded knowledge for a persistent wiki. "
        "Prefer useful, atomic, cited claims over broad generic summaries. "
        "Do not invent facts. If something is ambiguous, create a review item. "
        "Use domain-agnostic entity types such as person, organization, place, product, "
        "method, concept, event, dataset, metric, file, law, system, or other. "
        "Evidence locators must be stable and human-auditable, for example page 3, "
        "section 'Architecture', sheet 'Revenue'!A1:D20, image 2, or slide 5. "
        "For scanned PDFs/images, describe visual evidence and transcribed text "
        "as best as possible. "
        "Return only JSON that matches the requested schema."
    )


def _source_prompt(source: SourceRef) -> str:
    return (
        f"Source metadata:\n"
        f"- source_id: {source.id}\n"
        f"- title: {source.title}\n"
        f"- source_type: {source.source_type}\n"
        f"- sha256: {source.sha256}\n"
        f"- path: {source.path}\n\n"
        "Extract the strongest wiki-ready understanding from this source. "
        "Include the most important evidence items, claims, entities, review items, "
        "and open questions. Keep evidence concise but sufficient for later citation. "
        "If the source is long, prioritize durable claims, definitions, relationships, "
        "tables, figures, contradictions, and synthesis hooks that would help future queries."
    )


def _query_plan_instructions() -> str:
    return (
        "You are the query planner for a general-purpose LLM Wiki. "
        "Turn the user question into a domain-agnostic retrieval plan for SQLite FTS "
        "over evidence, claims, entities, and wiki pages. "
        "Prefer precise keywords, entity hints, and subquestions that improve recall. "
        "Do not answer the question. Return only JSON that matches the schema."
    )


def _evidence_ranking_instructions(max_evidence: int) -> str:
    return (
        "You are an evidence judge for a source-grounded LLM Wiki answer engine. "
        f"Select at most {max_evidence} evidence IDs that directly or strongly support "
        "answering the question. Reject weak, duplicate, or off-topic candidates. "
        "Call out contradictions and missing evidence explicitly. "
        "Do not invent evidence IDs. Return only JSON that matches the schema."
    )


def _query_synthesis_instructions() -> str:
    return (
        "You are the answer synthesizer for a source-grounded LLM Wiki chatbot. "
        "Answer only from the selected evidence supplied by the system. "
        "Every important factual claim must be backed by a citation using one of the "
        "provided evidence IDs. If the evidence is insufficient, say so and keep "
        "confidence as insufficient or low. Preserve the user's language when practical. "
        "Separate contradictions and open questions instead of hiding uncertainty. "
        "Return only JSON that matches the schema."
    )


def _candidate_payload(candidate: EvidenceCandidate) -> dict[str, object]:
    return {
        "evidence_id": candidate.evidence_id,
        "source_id": candidate.source_id,
        "source_title": candidate.source_title,
        "source_path": candidate.source_path,
        "wiki_page_path": candidate.wiki_page_path,
        "locator": candidate.locator,
        "modality": candidate.modality,
        "text": compact_text(candidate.text, 900),
        "summary": compact_text(candidate.summary, 400),
        "confidence": candidate.confidence,
        "claim_ids": candidate.claim_ids,
        "claims": [compact_text(claim, 400) for claim in candidate.claims],
        "entities": candidate.entities[:20],
        "retrieval_score": candidate.retrieval_score,
        "retrieval_channels": candidate.retrieval_channels,
    }
