import json

from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import llm_call_id
from backend.app.repositories.base import SQLiteRepository


class SQLiteOperationRepository(SQLiteRepository):
    def start(
        self,
        operation_id: str,
        operation_type: str,
        source_id: str | None,
        started_at: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO operations (
                    id, operation_type, source_id, status, started_at, metadata_json
                )
                VALUES (?, ?, ?, 'running', ?, ?)
                """,
                (
                    operation_id,
                    operation_type,
                    source_id,
                    started_at,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )

    def record_llm_call(self, operation_id: str, phase: str, usage) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_calls (
                    id, operation_id, phase, model, input_tokens,
                    output_tokens, latency_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    llm_call_id(),
                    operation_id,
                    phase,
                    usage.model,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.latency_ms,
                    utc_now_iso(),
                ),
            )

    def complete(
        self,
        operation_id: str,
        finished_at: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE operations
                SET status = 'completed', finished_at = ?, error = NULL,
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    finished_at,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    operation_id,
                ),
            )

    def fail(self, operation_id: str, finished_at: str, error: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE operations
                SET status = 'failed', finished_at = ?, error = ?
                WHERE id = ?
                """,
                (finished_at, error, operation_id),
            )

    def save_reviews(self, reviews: list) -> None:
        with self.database.connect() as connection:
            for review in reviews:
                connection.execute(
                    """
                    INSERT INTO review_items (
                        id, review_type, title, body, severity, status,
                        source_id, page_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review.id,
                        review.review_type,
                        review.title,
                        review.body,
                        review.severity,
                        review.status,
                        review.source_id,
                        review.page_id,
                        review.created_at,
                    ),
                )
