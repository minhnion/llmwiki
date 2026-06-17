from backend.app.domain.query import QueryAskCommand, QueryPlan
from backend.app.services.query_contracts import QueryLLMClient


class QueryPlanner:
    def __init__(self, llm_client: QueryLLMClient) -> None:
        self.llm_client = llm_client

    async def plan(self, command: QueryAskCommand) -> QueryPlan:
        return await self.llm_client.plan_query(command)
