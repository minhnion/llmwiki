from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from backend.app.application.container import AppContainer, get_container
from backend.app.application.factory import build_source_ingest
from backend.app.core.text import slugify
from backend.app.domain.models import SourceRef
from backend.app.repositories.operations import SQLiteOperationRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.source_ingest import SourceIngestResult
from backend.app.services.source_registry import RegisterSourceCommand, SourceRegistryService
from backend.app.services.wiki_log import WikiLogWriter

router = APIRouter(prefix="/sources", tags=["sources"])
ContainerDependency = Annotated[AppContainer, Depends(get_container)]


class RegisterSourceRequest(BaseModel):
    path: str
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
    ingested_at: str | None

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
            tags=source.tags,
            status=source.status,
            created_at=source.created_at,
            updated_at=source.updated_at,
            ingested_at=source.ingested_at,
        )


def build_source_registry(container: AppContainer) -> SourceRegistryService:
    return SourceRegistryService(
        source_repository=SQLiteSourceRepository(container.database),
        operation_repository=SQLiteOperationRepository(container.database),
        wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
    )


@router.post("/register", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def register_source(
    request: RegisterSourceRequest,
    container: ContainerDependency,
) -> SourceResponse:
    try:
        source = build_source_registry(container).register(
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


@router.post("/upload", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_source(
    container: ContainerDependency,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    source_type: Annotated[str | None, Form()] = None,
    tags: Annotated[list[str] | None, Form()] = None,
) -> SourceResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required.")
    upload_dir = container.settings.raw_dir / "sources"
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = _next_available_path(upload_dir / _safe_upload_name(file.filename))
    size = 0
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > container.settings.max_file_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Uploaded file exceeds maximum size: {size}",
                )
            output.write(chunk)
    try:
        source = build_source_registry(container).register(
            RegisterSourceCommand(
                path=destination,
                title=title or Path(file.filename).stem,
                source_type=source_type,
                tags=tuple(tags or []),
            )
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return SourceResponse.from_domain(source)


@router.get("", response_model=list[SourceResponse])
def list_sources(container: ContainerDependency) -> list[SourceResponse]:
    return [
        SourceResponse.from_domain(source)
        for source in SQLiteSourceRepository(container.database).list()
    ]


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: str, container: ContainerDependency) -> SourceResponse:
    source = SQLiteSourceRepository(container.database).get(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return SourceResponse.from_domain(source)


@router.post("/{source_id}/ingest", response_model=SourceIngestResult)
async def ingest_source(
    source_id: str,
    container: ContainerDependency,
    force: bool = Query(default=False),
) -> SourceIngestResult:
    try:
        return await build_source_ingest(container).ingest(source_id, force=force)
    except ValueError as exc:
        code = (
            status.HTTP_404_NOT_FOUND
            if "Source not found" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc


def _safe_upload_name(filename: str) -> str:
    path = Path(filename)
    stem = slugify(path.stem, fallback="upload")
    suffix = "".join(char for char in path.suffix.lower() if char.isalnum() or char == ".")
    return f"{stem}{suffix}"


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError("Could not allocate a unique upload path.")
