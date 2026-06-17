from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.application.container import AppContainer, get_container
from backend.app.domain.graph import (
    Contradiction,
    GraphBuildCommand,
    GraphBuildResult,
    GraphEntityDetail,
    GraphSearchResult,
)
from backend.app.repositories.graph import SQLiteGraphRepository
from backend.app.services.contradiction_detector import ContradictionDetector
from backend.app.services.entity_page_writer import EntityPageWriter
from backend.app.services.graph_builder import GraphBuilder
from backend.app.services.graph_extractor import GraphExtractor
from backend.app.services.llm_client import OpenAIResponsesClient
from backend.app.services.wiki_log import WikiLogWriter

router = APIRouter(prefix="/graph", tags=["graph"])
ContainerDependency = Annotated[AppContainer, Depends(get_container)]


def build_graph_builder(container: AppContainer) -> GraphBuilder:
    if not container.settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for graph build.")
    llm_client = OpenAIResponsesClient(
        api_key=container.settings.openai_api_key,
        model=container.settings.openai_model,
        max_output_tokens=container.settings.max_output_tokens,
    )
    return GraphBuilder(
        repository=SQLiteGraphRepository(container.database),
        extractor=GraphExtractor(llm_client),
        contradiction_detector=ContradictionDetector(llm_client),
        entity_page_writer=EntityPageWriter(container.settings.wiki_dir),
        wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
    )


@router.post("/build", response_model=GraphBuildResult)
async def build_graph(
    request: GraphBuildCommand,
    container: ContainerDependency,
) -> GraphBuildResult:
    try:
        return await build_graph_builder(container).build(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/search", response_model=GraphSearchResult)
def search_graph(
    q: Annotated[str, Query(min_length=1)],
    container: ContainerDependency,
) -> GraphSearchResult:
    return SQLiteGraphRepository(container.database).search_graph(q)


@router.get("/entities/{entity_id_or_name}", response_model=GraphEntityDetail)
def get_entity_detail(
    entity_id_or_name: str,
    container: ContainerDependency,
) -> GraphEntityDetail:
    detail = SQLiteGraphRepository(container.database).get_entity_detail(entity_id_or_name)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return detail


@router.get("/contradictions", response_model=list[Contradiction])
def list_contradictions(
    container: ContainerDependency,
    status_filter: str | None = Query(default="open", alias="status"),
) -> list[Contradiction]:
    return SQLiteGraphRepository(container.database).list_contradictions(status_filter)
