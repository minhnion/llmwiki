from typing import Protocol

from backend.app.domain.graph import (
    ClaimGraphContext,
    ContradictionDetectionResult,
    GraphExtractionResult,
)


class GraphLLMClient(Protocol):
    async def extract_graph_relations(
        self,
        claims: list[ClaimGraphContext],
    ) -> GraphExtractionResult:
        """Extract relation triples and entity merge candidates from claim contexts."""

    async def detect_contradictions(
        self,
        claims: list[ClaimGraphContext],
    ) -> ContradictionDetectionResult:
        """Detect contradictions or strong semantic tensions among claim contexts."""
