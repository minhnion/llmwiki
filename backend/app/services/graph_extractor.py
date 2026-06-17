from backend.app.domain.graph import ClaimGraphContext, GraphExtractionResult
from backend.app.services.graph_contracts import GraphLLMClient


class GraphExtractor:
    def __init__(self, llm_client: GraphLLMClient) -> None:
        self.llm_client = llm_client

    async def extract(self, claims: list[ClaimGraphContext]) -> GraphExtractionResult:
        if not claims:
            return GraphExtractionResult(relations=[], entity_merge_candidates=[], notes=[])
        return await self.llm_client.extract_graph_relations(claims)
