import asyncio
import base64
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from backend.app.domain.extraction import (
    INGEST_EXTRACTION_JSON_SCHEMA,
    IngestExtractionResult,
)
from backend.app.domain.models import SourceRef


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
        response = await asyncio.to_thread(
            self.client.responses.create,
            model=self.model,
            instructions=_ingest_instructions(),
            input=[
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
            text={
                "format": {
                    "type": "json_schema",
                    "name": "llm_wiki_ingest_extraction",
                    "schema": INGEST_EXTRACTION_JSON_SCHEMA,
                    "strict": True,
                }
            },
            max_output_tokens=self.max_output_tokens,
        )
        return IngestExtractionResult.model_validate(json.loads(response.output_text))


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
