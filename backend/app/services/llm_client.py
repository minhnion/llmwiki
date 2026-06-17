from dataclasses import dataclass, field
from typing import Protocol


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


class OpenAIResponsesClient:
    """Placeholder adapter for the OpenAI Responses API.

    The concrete API call will be implemented when the first ingest/query workflow
    is built. Keeping the adapter boundary now prevents OpenAI-specific code from
    leaking into domain logic.
    """

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def create_response(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("OpenAI Responses API integration is not implemented yet.")
