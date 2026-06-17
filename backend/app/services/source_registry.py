import mimetypes
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.core.clock import utc_now_iso
from backend.app.core.hashing import sha256_file
from backend.app.core.ids import ingest_job_id, source_id_from_hash, source_version_id
from backend.app.domain.models import SourceRef, SourceVersion
from backend.app.repositories.jobs import SQLiteIngestJobRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.services.wiki_log import WikiLogWriter


@dataclass(frozen=True)
class RegisterSourceCommand:
    path: Path
    title: str | None = None
    source_type: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


class SourceRegistryService:
    def __init__(
        self,
        source_repository: SQLiteSourceRepository,
        job_repository: SQLiteIngestJobRepository,
        wiki_log_writer: WikiLogWriter,
    ) -> None:
        self.source_repository = source_repository
        self.job_repository = job_repository
        self.wiki_log_writer = wiki_log_writer

    def register(self, command: RegisterSourceCommand) -> SourceRef:
        path = command.path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Source file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"Source path is not a file: {path}")

        sha256 = sha256_file(path)
        now = utc_now_iso()
        source = SourceRef(
            id=source_id_from_hash(sha256),
            title=command.title or path.stem,
            path=path,
            source_type=command.source_type or self._infer_source_type(path),
            sha256=sha256,
            mime_type=mimetypes.guess_type(path.name)[0],
            size_bytes=path.stat().st_size,
            tags=command.tags,
            status="registered",
            created_at=now,
            updated_at=now,
        )
        saved_source = self.source_repository.add(source)
        self.source_repository.add_version(
            SourceVersion(
                id=source_version_id(source.id, sha256),
                source_id=source.id,
                sha256=sha256,
                path=path,
                created_at=now,
            )
        )
        self.job_repository.create_register_job(ingest_job_id(), source.id, now)
        self.wiki_log_writer.append_source_registered(now, source.id, source.title, path)
        return saved_source

    @staticmethod
    def _infer_source_type(path: Path) -> str:
        suffix = path.suffix.lower().lstrip(".")
        if suffix:
            return suffix
        return "unknown"
