from backend.app.domain.query import (
    KnowledgeNavigationResult,
    NavigationArtifactSelection,
    QueryPlan,
)
from backend.app.repositories.semantic import SQLiteSemanticRepository
from backend.app.services.query_contracts import QueryLLMClient


class KnowledgeNavigator:
    def __init__(
        self,
        repository: SQLiteSemanticRepository,
        llm_client: QueryLLMClient,
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client

    async def navigate(
        self,
        question: str,
        plan: QueryPlan,
        source_ids: list[str],
        max_artifacts: int,
    ) -> KnowledgeNavigationResult:
        entries = self.repository.list_knowledge_map_entries(source_ids)
        valid_artifact_ids = {
            entry.artifact_id for entry in entries if entry.artifact_id is not None
        }
        valid_entry_ids = {entry.entry_id for entry in entries}
        if not entries or not valid_artifact_ids:
            return KnowledgeNavigationResult(
                selected_artifacts=[],
                relevant_map_entry_ids=[],
                missing_map_areas=["Knowledge map does not contain artifact entries."],
                reasoning_summary="No navigable artifact map was available.",
            )

        result = await self.llm_client.navigate_knowledge(
            question=question,
            plan=plan,
            map_entries=entries,
            max_artifacts=max_artifacts,
        )
        selected: list[NavigationArtifactSelection] = []
        seen: set[str] = set()
        for item in result.selected_artifacts:
            if item.artifact_id not in valid_artifact_ids or item.artifact_id in seen:
                continue
            selected.append(item)
            seen.add(item.artifact_id)
            if len(selected) >= max_artifacts:
                break
        return KnowledgeNavigationResult(
            selected_artifacts=selected,
            relevant_map_entry_ids=[
                entry_id
                for entry_id in result.relevant_map_entry_ids
                if entry_id in valid_entry_ids
            ],
            missing_map_areas=result.missing_map_areas,
            reasoning_summary=result.reasoning_summary,
        )
