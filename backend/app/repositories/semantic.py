import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass

from backend.app.core.text import stable_hash
from backend.app.domain.query import (
    ArtifactCandidate,
    ArtifactStatementCandidate,
    EvidenceCandidate,
    KnowledgeMapEntryCandidate,
    RetrievalSignal,
)
from backend.app.repositories.base import SQLiteRepository


@dataclass(frozen=True)
class ArtifactIndexRecord:
    artifact_id: str
    source_id: str
    artifact_type: str
    title: str
    aliases: list[str]
    summary: str
    content: str
    statements: list[str]
    relations: list[str]
    scope: list[str]
    confidence: float
    status: str
    review_status: str
    content_hash: str


@dataclass(frozen=True)
class ArtifactEmbeddingRecord:
    artifact_id: str
    source_id: str
    representation_type: str
    embedding_model: str
    vector: list[float]
    content_hash: str


@dataclass(frozen=True)
class ArtifactSearchHit:
    artifact_id: str
    channel: str
    rank: int
    score: float
    detail: str


class SQLiteSemanticRepository(SQLiteRepository):
    def list_artifacts_for_indexing(
        self,
        source_ids: list[str] | None = None,
    ) -> list[ArtifactIndexRecord]:
        source_ids = source_ids or []
        filter_sql, params = _source_filter_sql("a", "source_id", source_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    a.id,
                    a.source_id,
                    a.artifact_type,
                    a.title,
                    a.aliases_json,
                    a.summary,
                    a.content,
                    a.scope_json,
                    a.confidence,
                    a.status,
                    a.review_status,
                    COALESCE(av.content_hash, '') AS version_hash
                FROM artifacts a
                LEFT JOIN artifact_versions av
                    ON av.artifact_id = a.id
                    AND av.compiler_run_id = a.compiler_run_id
                WHERE 1 = 1
                {filter_sql}
                ORDER BY a.source_id, a.title, a.id
                """,
                tuple(params),
            ).fetchall()
            artifact_ids = [row["id"] for row in rows]
            statements_by_artifact = _index_statements_by_artifact(connection, artifact_ids)
            relations_by_artifact = _index_relations_by_artifact(connection, artifact_ids)
        return [
            ArtifactIndexRecord(
                artifact_id=row["id"],
                source_id=row["source_id"],
                artifact_type=row["artifact_type"],
                title=row["title"],
                aliases=json.loads(row["aliases_json"]),
                summary=row["summary"],
                content=row["content"],
                statements=statements_by_artifact[row["id"]],
                relations=relations_by_artifact[row["id"]],
                scope=_metadata_json_to_strings(row["scope_json"]),
                confidence=row["confidence"],
                status=row["status"],
                review_status=row["review_status"],
                content_hash=row["version_hash"]
                or stable_hash(
                    row["artifact_type"],
                    row["title"],
                    row["summary"],
                    row["content"],
                    row["aliases_json"],
                    row["scope_json"],
                    length=64,
                ),
            )
            for row in rows
        ]

    def embedding_content_hashes(
        self,
        embedding_model: str,
    ) -> dict[tuple[str, str], str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, representation_type, content_hash
                FROM artifact_embeddings
                WHERE embedding_model = ?
                """,
                (embedding_model,),
            ).fetchall()
        return {
            (row["artifact_id"], row["representation_type"]): row["content_hash"]
            for row in rows
        }

    def save_embeddings(
        self,
        embeddings: list[ArtifactEmbeddingRecord],
        timestamp: str,
    ) -> None:
        with self.database.connect() as connection:
            for item in embeddings:
                embedding_id = _embedding_id(
                    item.artifact_id,
                    item.representation_type,
                    item.embedding_model,
                )
                connection.execute(
                    """
                    INSERT INTO artifact_embeddings (
                        id, artifact_id, source_id, representation_type,
                        embedding_model, dimensions, vector_json, content_hash,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(artifact_id, representation_type, embedding_model)
                    DO UPDATE SET
                        source_id = excluded.source_id,
                        dimensions = excluded.dimensions,
                        vector_json = excluded.vector_json,
                        content_hash = excluded.content_hash,
                        updated_at = excluded.updated_at
                    """,
                    (
                        embedding_id,
                        item.artifact_id,
                        item.source_id,
                        item.representation_type,
                        item.embedding_model,
                        len(item.vector),
                        json.dumps(item.vector),
                        item.content_hash,
                        timestamp,
                        timestamp,
                    ),
                )

    def refresh_knowledge_map(self, timestamp: str) -> int:
        map_id = "kmap_global"
        with self.database.connect() as connection:
            page_rows = connection.execute(
                """
                SELECT id, source_id, path, title, page_type, summary
                FROM wiki_pages
                ORDER BY page_type, title, id
                """
            ).fetchall()
            linked_rows = connection.execute(
                """
                SELECT
                    wpa.page_id,
                    a.id AS artifact_id,
                    a.source_id,
                    a.artifact_type,
                    a.title,
                    a.summary,
                    a.confidence
                FROM wiki_page_artifacts wpa
                JOIN artifacts a ON a.id = wpa.artifact_id
                ORDER BY wpa.page_id, a.title, a.id
                """
            ).fetchall()
            artifact_rows = connection.execute(
                """
                SELECT id, source_id, artifact_type, title, summary, confidence
                FROM artifacts
                ORDER BY source_id, title, id
                """
            ).fetchall()

            page_count = len(page_rows)
            artifact_count = len(artifact_rows)
            map_payload = {
                "page_count": page_count,
                "artifact_count": artifact_count,
                "kind": "wiki-page-to-artifact-catalog",
            }
            content_hash = stable_hash(json.dumps(map_payload, sort_keys=True), length=64)
            connection.execute(
                """
                INSERT INTO knowledge_maps (
                    id, map_type, source_scope_json, title, summary, map_json,
                    content_hash, created_at, updated_at
                )
                VALUES (?, 'global', '[]', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(map_type, source_scope_json) DO UPDATE SET
                    title = excluded.title,
                    summary = excluded.summary,
                    map_json = excluded.map_json,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    map_id,
                    "Global artifact knowledge map",
                    "Hierarchical catalog from generated wiki pages to compiled artifacts.",
                    json.dumps(map_payload, sort_keys=True),
                    content_hash,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute("DELETE FROM knowledge_map_entries WHERE map_id = ?", (map_id,))

            entry_count = 0
            page_entry_ids: dict[str, str] = {}
            for row in page_rows:
                source_ids = [row["source_id"]] if row["source_id"] else []
                entry_id = _map_entry_id(map_id, "page", row["id"])
                page_entry_ids[row["id"]] = entry_id
                connection.execute(
                    """
                    INSERT INTO knowledge_map_entries (
                        id, map_id, parent_entry_id, page_id, artifact_id,
                        entry_type, title, summary, source_ids_json, confidence,
                        created_at, updated_at
                    )
                    VALUES (?, ?, NULL, ?, NULL, ?, ?, ?, ?, 1.0, ?, ?)
                    """,
                    (
                        entry_id,
                        map_id,
                        row["id"],
                        f"wiki_page:{row['page_type']}",
                        row["title"],
                        row["summary"],
                        json.dumps(source_ids),
                        timestamp,
                        timestamp,
                    ),
                )
                entry_count += 1

            linked_artifact_ids: set[str] = set()
            for row in linked_rows:
                linked_artifact_ids.add(row["artifact_id"])
                entry_id = _map_entry_id(map_id, "artifact", row["artifact_id"], row["page_id"])
                connection.execute(
                    """
                    INSERT INTO knowledge_map_entries (
                        id, map_id, parent_entry_id, page_id, artifact_id,
                        entry_type, title, summary, source_ids_json, confidence,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        map_id,
                        page_entry_ids.get(row["page_id"]),
                        row["page_id"],
                        row["artifact_id"],
                        f"artifact:{row['artifact_type']}",
                        row["title"],
                        row["summary"],
                        json.dumps([row["source_id"]]),
                        row["confidence"],
                        timestamp,
                        timestamp,
                    ),
                )
                entry_count += 1

            for row in artifact_rows:
                if row["id"] in linked_artifact_ids:
                    continue
                entry_id = _map_entry_id(map_id, "artifact", row["id"], "unlinked")
                connection.execute(
                    """
                    INSERT INTO knowledge_map_entries (
                        id, map_id, parent_entry_id, page_id, artifact_id,
                        entry_type, title, summary, source_ids_json, confidence,
                        created_at, updated_at
                    )
                    VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        map_id,
                        row["id"],
                        f"artifact:{row['artifact_type']}",
                        row["title"],
                        row["summary"],
                        json.dumps([row["source_id"]]),
                        row["confidence"],
                        timestamp,
                        timestamp,
                    ),
                )
                entry_count += 1
        return entry_count

    def list_knowledge_map_entries(
        self,
        source_ids: list[str],
        limit: int = 200,
    ) -> list[KnowledgeMapEntryCandidate]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id, parent_entry_id, page_id, artifact_id, entry_type,
                    title, summary, source_ids_json
                FROM knowledge_map_entries
                ORDER BY
                    CASE WHEN parent_entry_id IS NULL THEN 0 ELSE 1 END,
                    title,
                    id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        selected: list[KnowledgeMapEntryCandidate] = []
        requested_sources = set(source_ids)
        for row in rows:
            entry_source_ids = json.loads(row["source_ids_json"])
            if requested_sources and not requested_sources.intersection(entry_source_ids):
                continue
            selected.append(
                KnowledgeMapEntryCandidate(
                    entry_id=row["id"],
                    parent_entry_id=row["parent_entry_id"],
                    page_id=row["page_id"],
                    artifact_id=row["artifact_id"],
                    entry_type=row["entry_type"],
                    title=row["title"],
                    summary=row["summary"],
                    source_ids=entry_source_ids,
                )
            )
        return selected

    def search_artifact_fts(
        self,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[ArtifactSearchHit]:
        if not fts_query:
            return []
        hits: list[ArtifactSearchHit] = []
        with self.database.connect() as connection:
            for channel, rows in (
                (
                    "artifact_fts",
                    self._search_artifacts_fts(connection, fts_query, source_ids, tags, limit),
                ),
                (
                    "artifact_statement_fts",
                    self._search_statement_fts(connection, fts_query, source_ids, tags, limit),
                ),
                (
                    "artifact_relation_fts",
                    self._search_relation_fts(connection, fts_query, source_ids, tags, limit),
                ),
                (
                    "compiled_evidence_fts",
                    self._search_evidence_fts(connection, fts_query, source_ids, tags, limit),
                ),
                (
                    "wiki_page_fts",
                    self._search_wiki_page_fts(connection, fts_query, source_ids, tags, limit),
                ),
            ):
                for rank, artifact_id in enumerate(_dedupe(rows), start=1):
                    hits.append(
                        ArtifactSearchHit(
                            artifact_id=artifact_id,
                            channel=channel,
                            rank=rank,
                            score=1.0 / rank,
                            detail="SQLite FTS over compiled knowledge.",
                        )
                    )
        return hits

    def search_artifact_embeddings(
        self,
        query_vector: list[float],
        embedding_model: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[ArtifactSearchHit]:
        if not query_vector:
            return []
        filter_sql, params = _source_filter_sql("a", "source_id", source_ids)
        tag_sql, tag_params = _tag_filter_sql("src", tags)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    emb.artifact_id,
                    emb.representation_type,
                    emb.vector_json
                FROM artifact_embeddings emb
                JOIN artifacts a ON a.id = emb.artifact_id
                JOIN sources src ON src.id = a.source_id
                WHERE emb.embedding_model = ?
                {filter_sql}
                {tag_sql}
                """,
                (embedding_model, *params, *tag_params),
            ).fetchall()

        best_by_artifact: dict[str, tuple[float, str]] = {}
        for row in rows:
            similarity = _cosine_similarity(query_vector, json.loads(row["vector_json"]))
            current = best_by_artifact.get(row["artifact_id"])
            if current is None or similarity > current[0]:
                best_by_artifact[row["artifact_id"]] = (
                    similarity,
                    row["representation_type"],
                )

        ranked = sorted(best_by_artifact.items(), key=lambda item: item[1][0], reverse=True)
        return [
            ArtifactSearchHit(
                artifact_id=artifact_id,
                channel="artifact_embedding",
                rank=rank,
                score=score,
                detail=f"Best representation: {representation_type}",
            )
            for rank, (artifact_id, (score, representation_type)) in enumerate(
                ranked[:limit],
                start=1,
            )
        ]

    def expand_artifact_graph(
        self,
        seed_artifact_ids: list[str],
        source_ids: list[str],
        max_depth: int,
        max_nodes: int,
    ) -> dict[str, int]:
        if not seed_artifact_ids or max_depth <= 0 or max_nodes <= 0:
            return {}
        seed_ids = list(dict.fromkeys(seed_artifact_ids))
        discovered: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque((artifact_id, 0) for artifact_id in seed_ids)
        seen = set(seed_ids)
        with self.database.connect() as connection:
            while queue and len(discovered) < max_nodes:
                artifact_id, depth = queue.popleft()
                if depth >= max_depth:
                    continue
                neighbors = self._artifact_neighbors(connection, artifact_id, source_ids)
                for neighbor_id in neighbors:
                    if neighbor_id in seen:
                        continue
                    next_depth = depth + 1
                    seen.add(neighbor_id)
                    discovered[neighbor_id] = next_depth
                    if len(discovered) >= max_nodes:
                        break
                    queue.append((neighbor_id, next_depth))
        return discovered

    def hydrate_artifact_candidates(
        self,
        artifact_ids: list[str],
        score_by_id: dict[str, float],
        channels_by_id: dict[str, set[str]],
        signals_by_id: dict[str, list[RetrievalSignal]],
        graph_depth_by_id: dict[str, int] | None = None,
    ) -> list[ArtifactCandidate]:
        if not artifact_ids:
            return []
        graph_depth_by_id = graph_depth_by_id or {}
        ordered_ids = list(dict.fromkeys(artifact_ids))
        placeholders = ",".join("?" for _ in ordered_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    a.id,
                    a.source_id,
                    src.title AS source_title,
                    src.original_path AS source_path,
                    a.artifact_type,
                    a.title,
                    a.summary,
                    a.content,
                    a.aliases_json,
                    a.scope_json,
                    a.confidence,
                    a.status,
                    a.review_status,
                    COALESCE(
                        (
                            SELECT page.path
                            FROM wiki_page_artifacts wpa
                            JOIN wiki_pages page ON page.id = wpa.page_id
                            WHERE wpa.artifact_id = a.id
                            ORDER BY
                                CASE WHEN page.page_type = 'source' THEN 1 ELSE 0 END,
                                page.updated_at DESC,
                                page.path
                            LIMIT 1
                        ),
                        ''
                    ) AS wiki_page_path
                FROM artifacts a
                JOIN sources src ON src.id = a.source_id
                WHERE a.id IN ({placeholders})
                """,
                tuple(ordered_ids),
            ).fetchall()
            statements_by_artifact = self._statements_by_artifact(connection, ordered_ids)
            evidence_by_artifact = self._evidence_by_artifact(
                connection,
                ordered_ids,
                score_by_id,
                channels_by_id,
            )

        row_by_id = {row["id"]: row for row in rows}
        candidates: list[ArtifactCandidate] = []
        for artifact_id in ordered_ids:
            row = row_by_id.get(artifact_id)
            if row is None:
                continue
            candidates.append(
                ArtifactCandidate(
                    artifact_id=row["id"],
                    source_id=row["source_id"],
                    source_title=row["source_title"],
                    source_path=row["source_path"],
                    wiki_page_path=row["wiki_page_path"],
                    artifact_type=row["artifact_type"],
                    title=row["title"],
                    summary=row["summary"],
                    content=row["content"],
                    aliases=json.loads(row["aliases_json"]),
                    scope=_metadata_json_to_strings(row["scope_json"]),
                    confidence=row["confidence"],
                    status=row["status"],
                    review_status=row["review_status"],
                    statements=statements_by_artifact[row["id"]],
                    evidence=evidence_by_artifact[row["id"]],
                    retrieval_score=round(score_by_id.get(row["id"], 0.0), 6),
                    retrieval_channels=sorted(channels_by_id.get(row["id"], set())),
                    retrieval_signals=signals_by_id.get(row["id"], []),
                    graph_depth=graph_depth_by_id.get(row["id"], 0),
                )
            )
        return candidates

    def _search_artifacts_fts(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("a", "source_id", source_ids)
        tag_sql, tag_params = _tag_filter_sql("src", tags)
        rows = connection.execute(
            f"""
            SELECT a.id
            FROM artifacts_fts
            JOIN artifacts a ON a.id = artifacts_fts.id
            JOIN sources src ON src.id = a.source_id
            WHERE artifacts_fts MATCH ?
            {filter_sql}
            {tag_sql}
            ORDER BY bm25(artifacts_fts), a.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, *tag_params, limit),
        ).fetchall()
        return [row["id"] for row in rows]

    def _search_statement_fts(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("ast", "source_id", source_ids)
        tag_sql, tag_params = _tag_filter_sql("src", tags)
        rows = connection.execute(
            f"""
            SELECT ast.artifact_id
            FROM artifact_statements_fts
            JOIN artifact_statements ast ON ast.id = artifact_statements_fts.id
            JOIN sources src ON src.id = ast.source_id
            WHERE artifact_statements_fts MATCH ?
            {filter_sql}
            {tag_sql}
            ORDER BY bm25(artifact_statements_fts), ast.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, *tag_params, limit),
        ).fetchall()
        return [row["artifact_id"] for row in rows]

    def _search_relation_fts(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("a", "source_id", source_ids)
        tag_sql, tag_params = _tag_filter_sql("src", tags)
        rows = connection.execute(
            f"""
            SELECT ar.source_artifact_id, ar.target_artifact_id
            FROM artifact_relations_fts
            JOIN artifact_relations ar ON ar.id = artifact_relations_fts.id
            JOIN artifacts a ON a.id = ar.source_artifact_id
            JOIN sources src ON src.id = a.source_id
            WHERE artifact_relations_fts MATCH ?
            {filter_sql}
            {tag_sql}
            ORDER BY bm25(artifact_relations_fts), ar.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, *tag_params, limit),
        ).fetchall()
        artifact_ids: list[str] = []
        for row in rows:
            artifact_ids.append(row["source_artifact_id"])
            if row["target_artifact_id"]:
                artifact_ids.append(row["target_artifact_id"])
        return artifact_ids

    def _search_evidence_fts(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("ev", "source_id", source_ids)
        tag_sql, tag_params = _tag_filter_sql("src", tags)
        rows = connection.execute(
            f"""
            SELECT ae.artifact_id
            FROM evidence_items_fts
            JOIN evidence_items ev ON ev.id = evidence_items_fts.id
            JOIN artifact_evidence ae ON ae.evidence_id = ev.id
            JOIN sources src ON src.id = ev.source_id
            WHERE evidence_items_fts MATCH ?
            {filter_sql}
            {tag_sql}
            ORDER BY bm25(evidence_items_fts), ev.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, *tag_params, limit),
        ).fetchall()
        return [row["artifact_id"] for row in rows]

    def _search_wiki_page_fts(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("page", "source_id", source_ids)
        tag_sql, tag_params = _tag_filter_sql("src", tags)
        rows = connection.execute(
            f"""
            SELECT wpa.artifact_id
            FROM wiki_pages_fts
            JOIN wiki_pages page ON page.id = wiki_pages_fts.id
            JOIN wiki_page_artifacts wpa ON wpa.page_id = page.id
            JOIN sources src ON src.id = page.source_id
            WHERE wiki_pages_fts MATCH ?
            {filter_sql}
            {tag_sql}
            ORDER BY bm25(wiki_pages_fts)
            LIMIT ?
            """,
            (fts_query, *params, *tag_params, limit),
        ).fetchall()
        return [row["artifact_id"] for row in rows]

    def _artifact_neighbors(
        self,
        connection,
        artifact_id: str,
        source_ids: list[str],
    ) -> list[str]:
        source_filter, params = _source_filter_sql("a", "source_id", source_ids)
        rows = connection.execute(
            f"""
            SELECT neighbor_id
            FROM (
                SELECT ar.target_artifact_id AS neighbor_id, ar.confidence AS score
                FROM artifact_relations ar
                JOIN artifacts a ON a.id = ar.target_artifact_id
                WHERE ar.source_artifact_id = ?
                AND ar.target_artifact_id IS NOT NULL
                {source_filter}
                UNION ALL
                SELECT ar.source_artifact_id AS neighbor_id, ar.confidence AS score
                FROM artifact_relations ar
                JOIN artifacts a ON a.id = ar.source_artifact_id
                WHERE ar.target_artifact_id = ?
                {source_filter}
            )
            ORDER BY score DESC
            """,
            (artifact_id, *params, artifact_id, *params),
        ).fetchall()
        return [row["neighbor_id"] for row in rows if row["neighbor_id"]]

    def _statements_by_artifact(
        self,
        connection,
        artifact_ids: list[str],
    ) -> dict[str, list[ArtifactStatementCandidate]]:
        statements: dict[str, list[ArtifactStatementCandidate]] = defaultdict(list)
        if not artifact_ids:
            return statements
        placeholders = ",".join("?" for _ in artifact_ids)
        rows = connection.execute(
            f"""
            SELECT
                id, artifact_id, statement_type, statement_text, subject,
                predicate, object_value, confidence, status
            FROM artifact_statements
            WHERE artifact_id IN ({placeholders})
            ORDER BY confidence DESC, id
            """,
            tuple(artifact_ids),
        ).fetchall()
        statement_ids = [row["id"] for row in rows]
        evidence_by_statement: dict[str, list[str]] = defaultdict(list)
        if statement_ids:
            statement_placeholders = ",".join("?" for _ in statement_ids)
            evidence_rows = connection.execute(
                f"""
                SELECT statement_id, evidence_id
                FROM artifact_statement_evidence
                WHERE statement_id IN ({statement_placeholders})
                ORDER BY evidence_id
                """,
                tuple(statement_ids),
            ).fetchall()
            for row in evidence_rows:
                evidence_by_statement[row["statement_id"]].append(row["evidence_id"])
        for row in rows:
            statements[row["artifact_id"]].append(
                ArtifactStatementCandidate(
                    statement_id=row["id"],
                    statement_type=row["statement_type"],
                    text=row["statement_text"],
                    subject=row["subject"],
                    predicate=row["predicate"],
                    object=row["object_value"],
                    confidence=row["confidence"],
                    status=row["status"],
                    evidence_ids=evidence_by_statement[row["id"]],
                )
            )
        return statements

    def _evidence_by_artifact(
        self,
        connection,
        artifact_ids: list[str],
        score_by_id: dict[str, float],
        channels_by_id: dict[str, set[str]],
    ) -> dict[str, list[EvidenceCandidate]]:
        evidence_refs: dict[str, list[str]] = defaultdict(list)
        if not artifact_ids:
            return evidence_refs
        placeholders = ",".join("?" for _ in artifact_ids)
        rows = connection.execute(
            f"""
            SELECT artifact_id, evidence_id
            FROM artifact_evidence
            WHERE artifact_id IN ({placeholders})
            UNION
            SELECT ast.artifact_id, ase.evidence_id
            FROM artifact_statements ast
            JOIN artifact_statement_evidence ase ON ase.statement_id = ast.id
            WHERE ast.artifact_id IN ({placeholders})
            ORDER BY artifact_id, evidence_id
            """,
            (*artifact_ids, *artifact_ids),
        ).fetchall()
        evidence_ids: list[str] = []
        for row in rows:
            evidence_refs[row["artifact_id"]].append(row["evidence_id"])
            evidence_ids.append(row["evidence_id"])
        unique_evidence_ids = list(dict.fromkeys(evidence_ids))
        if not unique_evidence_ids:
            return defaultdict(list)
        evidence_placeholders = ",".join("?" for _ in unique_evidence_ids)
        evidence_rows = connection.execute(
            f"""
            SELECT
                ev.id AS evidence_id,
                ev.source_id,
                src.title AS source_title,
                src.original_path AS source_path,
                ev.locator,
                ev.modality,
                ev.text,
                ev.summary,
                ev.confidence
            FROM evidence_items ev
            JOIN sources src ON src.id = ev.source_id
            WHERE ev.id IN ({evidence_placeholders})
            """,
            tuple(unique_evidence_ids),
        ).fetchall()
        claim_rows = connection.execute(
            f"""
            SELECT ce.evidence_id, c.id AS claim_id, c.claim_text
            FROM claim_evidence ce
            JOIN claims c ON c.id = ce.claim_id
            WHERE ce.evidence_id IN ({evidence_placeholders})
            ORDER BY c.confidence DESC
            """,
            tuple(unique_evidence_ids),
        ).fetchall()
        claims_by_evidence: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in claim_rows:
            claims_by_evidence[row["evidence_id"]].append(
                (row["claim_id"], row["claim_text"])
            )
        entities_by_source = _entities_by_source(
            connection,
            [row["source_id"] for row in evidence_rows],
        )
        evidence_by_id = {
            row["evidence_id"]: EvidenceCandidate(
                evidence_id=row["evidence_id"],
                source_id=row["source_id"],
                source_title=row["source_title"],
                source_path=row["source_path"],
                wiki_page_path="",
                locator=row["locator"],
                modality=row["modality"],
                text=row["text"],
                summary=row["summary"],
                confidence=row["confidence"],
                claim_ids=[
                    claim_id for claim_id, _ in claims_by_evidence[row["evidence_id"]]
                ],
                claims=[text for _, text in claims_by_evidence[row["evidence_id"]]],
                entities=entities_by_source[row["source_id"]],
                retrieval_score=0.0,
                retrieval_channels=[],
            )
            for row in evidence_rows
        }
        evidence_by_artifact: dict[str, list[EvidenceCandidate]] = defaultdict(list)
        for artifact_id, refs in evidence_refs.items():
            for evidence_id in dict.fromkeys(refs):
                candidate = evidence_by_id.get(evidence_id)
                if candidate is None:
                    continue
                evidence_by_artifact[artifact_id].append(
                    candidate.model_copy(
                        update={
                            "retrieval_score": round(score_by_id.get(artifact_id, 0.0), 6),
                            "retrieval_channels": sorted(
                                channels_by_id.get(artifact_id, set())
                            ),
                        }
                    )
                )
        return evidence_by_artifact


def _metadata_json_to_strings(value: str) -> list[str]:
    items = json.loads(value)
    output: list[str] = []
    for item in items:
        if isinstance(item, dict):
            key = str(item.get("key", "")).strip()
            raw_value = str(item.get("value", "")).strip()
            if key and raw_value:
                output.append(f"{key}: {raw_value}")
            elif key:
                output.append(key)
            elif raw_value:
                output.append(raw_value)
        elif isinstance(item, str) and item.strip():
            output.append(item.strip())
    return output


def _embedding_id(
    artifact_id: str,
    representation_type: str,
    embedding_model: str,
) -> str:
    return f"aemb_{stable_hash(artifact_id, representation_type, embedding_model, length=20)}"


def _map_entry_id(map_id: str, entry_type: str, *parts: str) -> str:
    return f"kment_{stable_hash(map_id, entry_type, *parts, length=20)}"


def _source_filter_sql(alias: str, column: str, source_ids: list[str]) -> tuple[str, list[str]]:
    if not source_ids:
        return "", []
    placeholders = ",".join("?" for _ in source_ids)
    return f"AND {alias}.{column} IN ({placeholders})", list(source_ids)


def _tag_filter_sql(alias: str, tags: list[str]) -> tuple[str, list[str]]:
    if not tags:
        return "", []
    clauses = []
    params: list[str] = []
    for tag in tags:
        clauses.append(f"{alias}.tags_json LIKE ?")
        params.append(f'%"{tag}"%')
    return "AND (" + " OR ".join(clauses) + ")", params


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _entities_by_source(connection, source_ids: list[str]) -> dict[str, list[str]]:
    entities: dict[str, list[str]] = defaultdict(list)
    if not source_ids:
        return entities
    unique_source_ids = list(dict.fromkeys(source_ids))
    placeholders = ",".join("?" for _ in unique_source_ids)
    rows = connection.execute(
        f"""
        SELECT se.source_id, ent.canonical_name
        FROM source_entities se
        JOIN entities ent ON ent.id = se.entity_id
        WHERE se.source_id IN ({placeholders})
        ORDER BY ent.confidence DESC, ent.canonical_name ASC
        """,
        tuple(unique_source_ids),
    ).fetchall()
    for row in rows:
        entities[row["source_id"]].append(row["canonical_name"])
    return entities


def _index_statements_by_artifact(
    connection,
    artifact_ids: list[str],
) -> dict[str, list[str]]:
    statements: dict[str, list[str]] = defaultdict(list)
    if not artifact_ids:
        return statements
    placeholders = ",".join("?" for _ in artifact_ids)
    rows = connection.execute(
        f"""
        SELECT artifact_id, statement_text
        FROM artifact_statements
        WHERE artifact_id IN ({placeholders})
        ORDER BY confidence DESC, id
        """,
        tuple(artifact_ids),
    ).fetchall()
    for row in rows:
        statements[row["artifact_id"]].append(row["statement_text"])
    return statements


def _index_relations_by_artifact(
    connection,
    artifact_ids: list[str],
) -> dict[str, list[str]]:
    relations: dict[str, list[str]] = defaultdict(list)
    if not artifact_ids:
        return relations
    placeholders = ",".join("?" for _ in artifact_ids)
    rows = connection.execute(
        f"""
        SELECT
            ar.source_artifact_id,
            ar.target_artifact_id,
            ar.relation_type,
            ar.target_literal,
            target.title AS target_title
        FROM artifact_relations ar
        LEFT JOIN artifacts target ON target.id = ar.target_artifact_id
        WHERE ar.source_artifact_id IN ({placeholders})
        ORDER BY ar.confidence DESC, ar.relation_type, ar.id
        """,
        tuple(artifact_ids),
    ).fetchall()
    for row in rows:
        target = row["target_title"] or row["target_literal"] or row["target_artifact_id"] or ""
        relation_text = " ".join(
            part for part in [row["relation_type"], target] if str(part).strip()
        )
        if relation_text:
            relations[row["source_artifact_id"]].append(relation_text)
    return relations
