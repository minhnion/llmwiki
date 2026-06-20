import mimetypes
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.core.clock import utc_now_iso
from backend.app.core.hashing import sha256_file
from backend.app.core.ids import operation_id, source_id_from_hash, source_version_id
from backend.app.domain.models import SourceRef, SourceVersion
from backend.app.repositories.operations import SQLiteOperationRepository
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
        operation_repository: SQLiteOperationRepository,
        wiki_log_writer: WikiLogWriter,
    ) -> None:
        self.source_repository = source_repository
        self.operation_repository = operation_repository
        self.wiki_log_writer = wiki_log_writer

    def register(self, command: RegisterSourceCommand) -> SourceRef:
        path = command.path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Source file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"Source path is not a file: {path}")

        sha256 = sha256_file(path)
        now = utc_now_iso()
        current_operation_id = operation_id()
        self.operation_repository.start(
            current_operation_id,
            "register",
            None,
            now,
            {"path": str(path)},
        )
        try:
            source = SourceRef(
                id=source_id_from_hash(sha256),
                title=command.title or path.stem,
                path=path,
                source_type=command.source_type or _infer_source_type(path),
                sha256=sha256,
                mime_type=mimetypes.guess_type(path.name)[0],
                size_bytes=path.stat().st_size,
                tags=list(command.tags),
                status="registered",
                created_at=now,
                updated_at=now,
            )
            saved = self.source_repository.add(source)
            self.source_repository.add_version(
                SourceVersion(
                    id=source_version_id(source.id, sha256),
                    source_id=source.id,
                    sha256=sha256,
                    path=path,
                    created_at=now,
                )
            )
            self.operation_repository.complete(
                current_operation_id,
                utc_now_iso(),
                {"source_id": saved.id},
            )
            self.wiki_log_writer.append(
                now,
                "register",
                saved.title,
                {"source_id": saved.id, "path": str(path)},
            )
            return saved
        except Exception as exc:
            self.operation_repository.fail(current_operation_id, utc_now_iso(), str(exc))
            raise


def _infer_source_type(path: Path) -> str:
    return path.suffix.lower().lstrip(".") or "unknown"
