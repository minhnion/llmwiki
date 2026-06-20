from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.application.container import AppContainer, get_container
from backend.app.application.factory import build_wiki_store
from backend.app.domain.models import WikiPage, WikiPageSummary

router = APIRouter(prefix="/wiki", tags=["wiki"])
ContainerDependency = Annotated[AppContainer, Depends(get_container)]


@router.get("/pages", response_model=list[WikiPageSummary])
def list_pages(container: ContainerDependency) -> list[WikiPageSummary]:
    store = build_wiki_store(container)
    store.rebuild()
    return store.catalog()


@router.get("/pages/{page_id}", response_model=WikiPage)
def get_page(page_id: str, container: ContainerDependency) -> WikiPage:
    pages = build_wiki_store(container).get_pages([page_id])
    if not pages:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return pages[0]


@router.post("/rebuild", response_model=list[WikiPageSummary])
def rebuild_wiki(container: ContainerDependency) -> list[WikiPageSummary]:
    store = build_wiki_store(container)
    store.rebuild()
    return store.catalog()
