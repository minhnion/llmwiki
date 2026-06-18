from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.application.container import AppContainer, get_container
from backend.app.domain.query import QueryAskCommand, QueryResult
from backend.app.repositories.query import SQLiteQueryRepository
from backend.app.services.answer_synthesizer import AnswerSynthesizer
from backend.app.services.evidence_ranker import EvidenceRanker
from backend.app.services.llm_client import OpenAIResponsesClient
from backend.app.services.query_engine import QueryEngine
from backend.app.services.query_planner import QueryPlanner
from backend.app.services.wiki_log import WikiLogWriter

router = APIRouter(prefix="/query", tags=["query"])
ContainerDependency = Annotated[AppContainer, Depends(get_container)]


def build_query_engine(container: AppContainer) -> QueryEngine:
    if not container.settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for query synthesis.")
    llm_client = OpenAIResponsesClient(
        api_key=container.settings.openai_api_key,
        model=container.settings.openai_model,
        max_output_tokens=container.settings.max_output_tokens,
        preferred_language=container.settings.preferred_language,
    )
    return QueryEngine(
        repository=SQLiteQueryRepository(container.database),
        planner=QueryPlanner(llm_client),
        ranker=EvidenceRanker(llm_client),
        synthesizer=AnswerSynthesizer(llm_client),
        wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
    )


@router.post("", response_model=QueryResult)
async def ask_query(
    request: QueryAskCommand,
    container: ContainerDependency,
) -> QueryResult:
    try:
        engine = build_query_engine(container)
        return await engine.ask(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
