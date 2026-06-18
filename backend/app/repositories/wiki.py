import json

from backend.app.domain.models import WikiPage
from backend.app.repositories.base import SQLiteRepository


class SQLiteWikiRepository(SQLiteRepository):
    def list_source_page_paths(self, source_id: str) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT path FROM wiki_pages WHERE source_id = ?",
                (source_id,),
            ).fetchall()
        return [row["path"] for row in rows]

    def save_pages(self, source_id: str, pages: list[WikiPage]) -> None:
        with self.database.connect() as connection:
            for page in pages:
                connection.execute(
                    """
                    INSERT INTO wiki_pages (
                        id, source_id, path, title, page_type, summary,
                        sha256, created_at, updated_at, frontmatter_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        title = excluded.title,
                        page_type = excluded.page_type,
                        summary = excluded.summary,
                        sha256 = excluded.sha256,
                        updated_at = excluded.updated_at,
                        frontmatter_json = excluded.frontmatter_json
                    """,
                    (
                        page.id,
                        source_id,
                        str(page.path),
                        page.title,
                        page.page_type,
                        page.summary,
                        page.sha256 or "",
                        page.created_at,
                        page.updated_at,
                        json.dumps(
                            {
                                "source_ids": list(page.source_ids),
                                "artifact_ids": list(page.artifact_ids),
                                "claim_ids": list(page.claim_ids),
                            }
                        ),
                    ),
                )
                connection.execute(
                    "DELETE FROM wiki_pages_fts WHERE id = ?",
                    (page.id,),
                )
                connection.execute(
                    """
                    INSERT INTO wiki_pages_fts (id, path, title, summary, body)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (page.id, str(page.path), page.title, page.summary, page.body),
                )
                connection.execute(
                    "DELETE FROM wiki_page_artifacts WHERE page_id = ?",
                    (page.id,),
                )
                for artifact_id in page.artifact_ids:
                    connection.execute(
                        """
                        INSERT INTO wiki_page_artifacts (page_id, artifact_id)
                        VALUES (?, ?)
                        """,
                        (page.id, artifact_id),
                    )
                connection.execute(
                    "DELETE FROM wiki_links WHERE from_page_id = ?",
                    (page.id,),
                )
            for page in pages:
                for related_page_id in page.related_page_ids:
                    connection.execute(
                        """
                        INSERT INTO wiki_links (
                            from_page_id, to_page_id, link_type, created_at
                        )
                        VALUES (?, ?, 'related', ?)
                        """,
                        (page.id, related_page_id, page.updated_at),
                    )
