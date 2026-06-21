import json

from backend.app.domain.agent import QueryResult
from backend.app.repositories.base import SQLiteRepository


class SQLiteQueryRepository(SQLiteRepository):
    def save(self, result: QueryResult) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO query_runs (
                    id, question, mode, answer, confidence, citations_json,
                    pages_read_json, sources_inspected_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.query_id,
                    result.question,
                    result.mode,
                    result.answer,
                    result.confidence,
                    json.dumps(
                        [item.model_dump() for item in result.citations],
                        ensure_ascii=False,
                    ),
                    json.dumps(result.pages_read, ensure_ascii=False),
                    json.dumps(result.sources_inspected, ensure_ascii=False),
                    result.created_at,
                ),
            )
