import json
from pathlib import Path

from backend.app.domain.contracts import SourceRepository
from backend.app.domain.models import SourceRef, SourceVersion
from backend.app.repositories.base import SQLiteRepository


class SQLiteSourceRepository(SQLiteRepository, SourceRepository):
    def add(self, source: SourceRef) -> SourceRef:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sources (
                    id, title, source_type, original_path, sha256, mime_type,
                    size_bytes, tags_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sha256) DO UPDATE SET
                    title = excluded.title,
                    source_type = excluded.source_type,
                    original_path = excluded.original_path,
                    mime_type = excluded.mime_type,
                    size_bytes = excluded.size_bytes,
                    tags_json = excluded.tags_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    source.id,
                    source.title,
                    source.source_type,
                    str(source.path),
                    source.sha256,
                    source.mime_type,
                    source.size_bytes,
                    json.dumps(list(source.tags)),
                    source.status,
                    source.created_at,
                    source.updated_at,
                ),
            )
        return self.get(source.id) or source

    def add_version(self, version: SourceVersion) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO source_versions (
                    id, source_id, sha256, path, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    version.id,
                    version.source_id,
                    version.sha256,
                    str(version.path),
                    version.created_at,
                ),
            )

    def get(self, source_id: str) -> SourceRef | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_source(row)

    def list(self) -> list[SourceRef]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sources ORDER BY created_at DESC, title ASC",
            ).fetchall()
        return [self._row_to_source(row) for row in rows]

    def mark_ingested(self, source_id: str, ingested_at: str) -> SourceRef | None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE sources
                SET status = 'ingested', ingested_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (ingested_at, ingested_at, source_id),
            )
        return self.get(source_id)

    @staticmethod
    def _row_to_source(row: object) -> SourceRef:
        return SourceRef(
            id=row["id"],
            title=row["title"],
            path=Path(row["original_path"]),
            source_type=row["source_type"],
            sha256=row["sha256"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            tags=tuple(json.loads(row["tags_json"])),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
