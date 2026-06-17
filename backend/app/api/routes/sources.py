from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.application.container import AppContainer, get_container
from backend.app.domain.models import SourceRef
from backend.app.repositories.extractions import SQLiteExtractionRepository
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.llm_client import OpenAIResponsesClient
from backend.app.services.source_ingest import SourceIngestResult, SourceIngestService
from backend.app.services.source_page_writer import SourcePageWriter
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter

router = APIRouter(prefix="/sources", tags=["sources"])
ContainerDependency = Annotated[AppContainer, Depends(get_container)]


class RegisterSourceRequest(BaseModel):
    path: str = Field(..., description="Path to a local source file.")
    title: str | None = None
    source_type: str | None = None
    tags: list[str] = Field(default_factory=list)


class SourceResponse(BaseModel):
    id: str
    title: str
    path: str
    source_type: str
    sha256: str
    mime_type: str | None
    size_bytes: int | None
    tags: list[str]
    status: str
    created_at: str | None
    updated_at: str | None

    @classmethod
    def from_domain(cls, source: SourceRef) -> "SourceResponse":
        return cls(
            id=source.id,
            title=source.title,
            path=str(source.path),
            source_type=source.source_type,
            sha256=source.sha256,
            mime_type=source.mime_type,
            size_bytes=source.size_bytes,
            tags=list(source.tags),
            status=source.status,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )


class SourceIngestResponse(BaseModel):
    source: SourceResponse
    page_path: str
    evidence_count: int
    claim_count: int
    entity_count: int
    review_item_count: int

    @classmethod
    def from_domain(cls, result: SourceIngestResult) -> "SourceIngestResponse":
        return cls(
            source=SourceResponse.from_domain(result.source),
            page_path=str(result.page.path),
            evidence_count=len(result.extraction.evidence_items),
            claim_count=len(result.extraction.claims),
            entity_count=len(result.extraction.entities),
            review_item_count=len(result.extraction.review_items),
        )


def build_source_registry(container: AppContainer) -> SourceRegistryService:
    return SourceRegistryService(
        source_repository=SQLiteSourceRepository(container.database),
        job_repository=SQLiteIngestJobRepository(container.database),
        wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
    )


def build_source_ingest(container: AppContainer) -> SourceIngestService:
    if not container.settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for ingest.")
    return SourceIngestService(
        source_repository=SQLiteSourceRepository(container.database),
        extraction_repository=SQLiteExtractionRepository(container.database),
        job_repository=SQLiteIngestJobRepository(container.database),
        llm_client=OpenAIResponsesClient(
            api_key=container.settings.openai_api_key,
            model=container.settings.openai_model,
            max_output_tokens=container.settings.max_output_tokens,
        ),
        source_page_writer=SourcePageWriter(container.settings.wiki_dir),
        wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
        max_file_bytes=container.settings.max_file_bytes,
    )


@router.post("/register", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def register_source(
    request: RegisterSourceRequest,
    container: ContainerDependency,
) -> SourceResponse:
    service = build_source_registry(container)
    try:
        source = service.register(
            RegisterSourceCommand(
                path=Path(request.path),
                title=request.title,
                source_type=request.source_type,
                tags=tuple(request.tags),
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SourceResponse.from_domain(source)


@router.get("", response_model=list[SourceResponse])
def list_sources(container: ContainerDependency) -> list[SourceResponse]:
    repository = SQLiteSourceRepository(container.database)
    return [SourceResponse.from_domain(source) for source in repository.list()]


@router.post("/{source_id}/ingest", response_model=SourceIngestResponse)
async def ingest_source(source_id: str, container: ContainerDependency) -> SourceIngestResponse:
    try:
        service = build_source_ingest(container)
        result = await service.ingest(source_id)
    except ValueError as exc:
        message = str(exc)
        http_status = (
            status.HTTP_404_NOT_FOUND
            if "Source not found" in message
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=http_status, detail=message) from exc
    return SourceIngestResponse.from_domain(result)


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: str, container: ContainerDependency) -> SourceResponse:
    repository = SQLiteSourceRepository(container.database)
    source = repository.get(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return SourceResponse.from_domain(source)
