from collections import defaultdict

from backend.app.core.hashing import sha256_file
from backend.app.domain.models import EvidenceRef, WikiPage, WikiPageSummary
from backend.app.repositories.base import SQLiteRepository


class SQLiteWikiRepository(SQLiteRepository):
    def sync(self, pages: list[WikiPage], links: dict[str, set[str]]) -> None:
        page_ids = {page.id for page in pages}
        with self.database.connect() as connection:
            existing_ids = {
                row["id"] for row in connection.execute("SELECT id FROM wiki_pages")
            }
            stale_ids = existing_ids - page_ids
            for stale_id in stale_ids:
                connection.execute("DELETE FROM wiki_pages_fts WHERE id = ?", (stale_id,))
                connection.execute("DELETE FROM wiki_pages WHERE id = ?", (stale_id,))

            for page in pages:
                connection.execute(
                    """
                    INSERT INTO wiki_pages (
                        id, path, title, page_type, summary, status, confidence,
                        body_hash, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        path = excluded.path,
                        title = excluded.title,
                        page_type = excluded.page_type,
                        summary = excluded.summary,
                        status = excluded.status,
                        confidence = excluded.confidence,
                        body_hash = excluded.body_hash,
                        updated_at = excluded.updated_at
                    """,
                    (
                        page.id,
                        str(page.path),
                        page.title,
                        page.page_type,
                        page.summary,
                        page.status,
                        page.confidence,
                        sha256_file(page.path),
                        page.created_at,
                        page.updated_at,
                    ),
                )
                connection.execute("DELETE FROM wiki_pages_fts WHERE id = ?", (page.id,))
                connection.execute(
                    """
                    INSERT INTO wiki_pages_fts (
                        id, path, title, page_type, summary, body
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        page.id,
                        str(page.path),
                        page.title,
                        page.page_type,
                        page.summary,
                        page.body,
                    ),
                )
                connection.execute("DELETE FROM page_sources WHERE page_id = ?", (page.id,))
                connection.execute("DELETE FROM evidence_refs WHERE page_id = ?", (page.id,))
                for evidence in page.evidence_refs:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO page_sources (page_id, source_id)
                        VALUES (?, ?)
                        """,
                        (page.id, evidence.source_id),
                    )
                    connection.execute(
                        """
                        INSERT INTO evidence_refs (
                            id, page_id, source_id, locator, quote_or_summary,
                            modality, confidence
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            evidence.id,
                            page.id,
                            evidence.source_id,
                            evidence.locator,
                            evidence.quote_or_summary,
                            evidence.modality,
                            evidence.confidence,
                        ),
                    )

            connection.execute("DELETE FROM wiki_links")
            for from_page_id, targets in links.items():
                if from_page_id not in page_ids:
                    continue
                for to_page_id in sorted(targets & page_ids):
                    connection.execute(
                        """
                        INSERT INTO wiki_links (from_page_id, to_page_id, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (from_page_id, to_page_id, _page_timestamp(pages, from_page_id)),
                    )

    def list_summaries(self, source_ids: list[str] | None = None) -> list[WikiPageSummary]:
        source_ids = source_ids or []
        filter_sql = ""
        params: list[str] = []
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            filter_sql = (
                "WHERE EXISTS (SELECT 1 FROM page_sources ps "
                f"WHERE ps.page_id = p.id AND ps.source_id IN ({placeholders}))"
            )
            params.extend(source_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT p.*
                FROM wiki_pages p
                {filter_sql}
                ORDER BY p.page_type, p.title, p.id
                """,
                tuple(params),
            ).fetchall()
            sources_by_page = _sources_by_page(connection, [row["id"] for row in rows])
        return [
            WikiPageSummary(
                id=row["id"],
                path=row["path"],
                title=row["title"],
                page_type=row["page_type"],
                summary=row["summary"],
                status=row["status"],
                confidence=row["confidence"],
                source_ids=sources_by_page[row["id"]],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def search(
        self,
        query: str,
        limit: int,
        source_ids: list[str] | None = None,
    ) -> list[str]:
        fts_query = _fts_query(query)
        if not fts_query:
            return []
        source_ids = source_ids or []
        filter_sql = ""
        params: list[object] = [fts_query]
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            filter_sql = (
                "AND EXISTS (SELECT 1 FROM page_sources ps "
                f"WHERE ps.page_id = p.id AND ps.source_id IN ({placeholders}))"
            )
            params.extend(source_ids)
        params.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT p.id
                FROM wiki_pages_fts
                JOIN wiki_pages p ON p.id = wiki_pages_fts.id
                WHERE wiki_pages_fts MATCH ?
                {filter_sql}
                ORDER BY bm25(wiki_pages_fts), p.confidence DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [row["id"] for row in rows]

    def evidence_for_pages(self, page_ids: list[str]) -> dict[str, list[EvidenceRef]]:
        output: dict[str, list[EvidenceRef]] = defaultdict(list)
        if not page_ids:
            return output
        placeholders = ",".join("?" for _ in page_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM evidence_refs
                WHERE page_id IN ({placeholders})
                ORDER BY page_id, source_id, locator, id
                """,
                tuple(page_ids),
            ).fetchall()
        for row in rows:
            output[row["page_id"]].append(
                EvidenceRef(
                    id=row["id"],
                    source_id=row["source_id"],
                    locator=row["locator"],
                    quote_or_summary=row["quote_or_summary"],
                    modality=row["modality"],
                    confidence=row["confidence"],
                )
            )
        return output


def _sources_by_page(connection, page_ids: list[str]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = defaultdict(list)
    if not page_ids:
        return output
    placeholders = ",".join("?" for _ in page_ids)
    rows = connection.execute(
        f"""
        SELECT page_id, source_id
        FROM page_sources
        WHERE page_id IN ({placeholders})
        ORDER BY source_id
        """,
        tuple(page_ids),
    ).fetchall()
    for row in rows:
        output[row["page_id"]].append(row["source_id"])
    return output


def _fts_query(value: str) -> str:
    terms = []
    for raw in value.split():
        term = raw.strip().replace('"', '""')
        if term:
            terms.append(f'"{term}"')
    return " OR ".join(dict.fromkeys(terms))


def _page_timestamp(pages: list[WikiPage], page_id: str) -> str:
    for page in pages:
        if page.id == page_id:
            return page.updated_at
    raise KeyError(page_id)
