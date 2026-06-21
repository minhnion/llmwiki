from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.application.container import AppContainer, get_container
from backend.app.application.factory import build_query_agent
from backend.app.domain.agent import QueryAskCommand, QueryResult

router = APIRouter(prefix="/query", tags=["query"])
ContainerDependency = Annotated[AppContainer, Depends(get_container)]


@router.post("", response_model=QueryResult)
async def ask_query(
    request: QueryAskCommand,
    container: ContainerDependency,
) -> QueryResult:
    try:
        return await build_query_agent(container).ask(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
