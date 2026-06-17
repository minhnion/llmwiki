import json

from backend.app.repositories.base import SQLiteRepository


class SQLiteIngestJobRepository(SQLiteRepository):
    def create_register_job(self, job_id: str, source_id: str, created_at: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO ingest_jobs (
                    id, source_id, job_type, status, created_at,
                    started_at, finished_at, metadata_json
                )
                VALUES (?, ?, 'register', 'completed', ?, ?, ?, ?)
                """,
                (
                    job_id,
                    source_id,
                    created_at,
                    created_at,
                    created_at,
                    json.dumps({"phase": "source_registry"}),
                ),
            )

    def create_ingest_job(self, job_id: str, source_id: str, created_at: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO ingest_jobs (
                    id, source_id, job_type, status, created_at, started_at, metadata_json
                )
                VALUES (?, ?, 'ingest', 'running', ?, ?, ?)
                """,
                (
                    job_id,
                    source_id,
                    created_at,
                    created_at,
                    json.dumps({"phase": "multimodal_ingest"}),
                ),
            )

    def mark_completed(self, job_id: str, finished_at: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE ingest_jobs
                SET status = 'completed', finished_at = ?, error = NULL
                WHERE id = ?
                """,
                (finished_at, job_id),
            )

    def mark_failed(self, job_id: str, finished_at: str, error: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE ingest_jobs
                SET status = 'failed', finished_at = ?, error = ?
                WHERE id = ?
                """,
                (finished_at, error, job_id),
            )
