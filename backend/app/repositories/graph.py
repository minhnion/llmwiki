import json
import re
from collections import defaultdict

from backend.app.core.ids import (
    contradiction_id,
    entity_merge_candidate_id,
    relation_edge_id,
)
from backend.app.domain.graph import (
    ClaimEvidenceContext,
    ClaimGraphContext,
    Contradiction,
    EntityMergeCandidate,
    ExtractedContradiction,
    ExtractedEntityMergeCandidate,
    ExtractedRelation,
    GraphBuildResult,
    GraphEdge,
    GraphEntity,
    GraphEntityDetail,
    GraphNode,
    GraphSearchResult,
    GraphVisualization,
    RelationEdge,
)
from backend.app.domain.models import WikiPage
from backend.app.repositories.base import SQLiteRepository


class SQLiteGraphRepository(SQLiteRepository):
    def create_graph_run(
        self,
        graph_run_id: str,
        source_ids: list[str],
        started_at: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO graph_runs (
                    id, status, source_ids_json, created_at
                )
                VALUES (?, 'running', ?, ?)
                """,
                (graph_run_id, json.dumps(source_ids), started_at),
            )

    def finish_graph_run(self, result: GraphBuildResult) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE graph_runs
                SET status = ?, claim_count = ?, relation_count = ?,
                    contradiction_count = ?, merge_candidate_count = ?,
                    entity_page_count = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    result.status,
                    result.claim_count,
                    result.relation_count,
                    result.contradiction_count,
                    result.merge_candidate_count,
                    result.entity_page_count,
                    result.finished_at,
                    result.graph_run_id,
                ),
            )

    def fail_graph_run(self, graph_run_id: str, finished_at: str, error: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE graph_runs
                SET status = 'failed', finished_at = ?, error = ?
                WHERE id = ?
                """,
                (finished_at, error, graph_run_id),
            )

    def clear_graph_artifacts(self, source_ids: list[str]) -> None:
        with self.database.connect() as connection:
            if not source_ids:
                connection.execute("DELETE FROM relation_edges_fts")
                connection.execute("DELETE FROM relation_edges")
                connection.execute("DELETE FROM contradictions")
                connection.execute("DELETE FROM entity_merge_candidates")
                return

            placeholders = ",".join("?" for _ in source_ids)
            relation_rows = connection.execute(
                f"SELECT id FROM relation_edges WHERE source_id IN ({placeholders})",
                tuple(source_ids),
            ).fetchall()
            for row in relation_rows:
                connection.execute("DELETE FROM relation_edges_fts WHERE id = ?", (row["id"],))
            connection.execute(
                f"DELETE FROM relation_edges WHERE source_id IN ({placeholders})",
                tuple(source_ids),
            )
            claim_rows = connection.execute(
                f"SELECT id FROM claims WHERE source_id IN ({placeholders})",
                tuple(source_ids),
            ).fetchall()
            claim_ids = [row["id"] for row in claim_rows]
            if claim_ids:
                claim_placeholders = ",".join("?" for _ in claim_ids)
                connection.execute(
                    f"""
                    DELETE FROM contradictions
                    WHERE claim_a_id IN ({claim_placeholders})
                    OR claim_b_id IN ({claim_placeholders})
                    """,
                    (*claim_ids, *claim_ids),
                )
            connection.execute("DELETE FROM entity_merge_candidates")

    def sync_entity_aliases(self, created_at: str) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM entity_aliases")
            rows = connection.execute(
                "SELECT id, canonical_name, aliases_json, confidence FROM entities"
            ).fetchall()
            for row in rows:
                aliases = [row["canonical_name"], *json.loads(row["aliases_json"])]
                for alias in dict.fromkeys(alias for alias in aliases if alias.strip()):
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO entity_aliases (
                            entity_id, alias, normalized_alias, source,
                            confidence, created_at
                        )
                        VALUES (?, ?, ?, 'ingest', ?, ?)
                        """,
                        (
                            row["id"],
                            alias,
                            _normalize_name(alias),
                            row["confidence"],
                            created_at,
                        ),
                    )

    def list_claim_contexts(self, source_ids: list[str]) -> list[ClaimGraphContext]:
        filter_sql, params = _source_filter_sql("c", "source_id", source_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    c.id,
                    c.source_id,
                    s.title AS source_title,
                    c.claim_text,
                    c.normalized_subject,
                    c.normalized_predicate,
                    c.normalized_object,
                    c.status,
                    c.confidence
                FROM claims c
                JOIN sources s ON s.id = c.source_id
                WHERE 1 = 1
                {filter_sql}
                ORDER BY c.source_id, c.created_at, c.id
                """,
                tuple(params),
            ).fetchall()
            claim_ids = [row["id"] for row in rows]
            evidence_by_claim = self._evidence_by_claim(connection, claim_ids)
            entities_by_source = self._entities_by_source(
                connection,
                [row["source_id"] for row in rows],
            )

        return [
            ClaimGraphContext(
                claim_id=row["id"],
                source_id=row["source_id"],
                source_title=row["source_title"],
                text=row["claim_text"],
                subject=row["normalized_subject"],
                predicate=row["normalized_predicate"],
                object=row["normalized_object"],
                status=row["status"],
                confidence=row["confidence"],
                evidence=evidence_by_claim[row["id"]],
                entities=entities_by_source[row["source_id"]],
            )
            for row in rows
        ]

    def save_relations(
        self,
        relations: list[ExtractedRelation],
        contexts: list[ClaimGraphContext],
        timestamp: str,
    ) -> list[RelationEdge]:
        contexts_by_claim = {context.claim_id: context for context in contexts}
        saved: list[RelationEdge] = []
        with self.database.connect() as connection:
            for relation in relations:
                context = contexts_by_claim.get(relation.claim_id)
                if context is None:
                    continue
                valid_evidence_ids = {evidence.evidence_id for evidence in context.evidence}
                if relation.evidence_id not in valid_evidence_ids:
                    continue
                subject_entity_id = self._resolve_entity_id(connection, relation.subject)
                object_entity_id = (
                    self._resolve_entity_id(connection, relation.object)
                    if relation.object_type == "entity"
                    else None
                )
                current_relation_id = relation_edge_id(
                    relation.claim_id,
                    relation.evidence_id,
                    relation.subject,
                    relation.predicate,
                    relation.object,
                )
                edge = RelationEdge(
                    id=current_relation_id,
                    subject_entity_id=subject_entity_id,
                    subject_name=relation.subject,
                    predicate=relation.predicate,
                    object_entity_id=object_entity_id,
                    object_value=relation.object,
                    object_type=relation.object_type,
                    claim_id=relation.claim_id,
                    evidence_id=relation.evidence_id,
                    source_id=context.source_id,
                    confidence=relation.confidence,
                    status=relation.status,
                    qualifiers=relation.qualifiers,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                connection.execute(
                    """
                    INSERT INTO relation_edges (
                        id, subject_entity_id, subject_name, predicate,
                        object_entity_id, object_value, object_type, claim_id,
                        evidence_id, source_id, confidence, status,
                        qualifiers_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        subject_entity_id = excluded.subject_entity_id,
                        subject_name = excluded.subject_name,
                        predicate = excluded.predicate,
                        object_entity_id = excluded.object_entity_id,
                        object_value = excluded.object_value,
                        object_type = excluded.object_type,
                        confidence = excluded.confidence,
                        status = excluded.status,
                        qualifiers_json = excluded.qualifiers_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        edge.id,
                        edge.subject_entity_id,
                        edge.subject_name,
                        edge.predicate,
                        edge.object_entity_id,
                        edge.object_value,
                        edge.object_type,
                        edge.claim_id,
                        edge.evidence_id,
                        edge.source_id,
                        edge.confidence,
                        edge.status,
                        json.dumps(edge.qualifiers),
                        edge.created_at,
                        edge.updated_at,
                    ),
                )
                connection.execute("DELETE FROM relation_edges_fts WHERE id = ?", (edge.id,))
                connection.execute(
                    """
                    INSERT INTO relation_edges_fts (
                        id, source_id, subject_name, predicate,
                        object_value, object_type, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge.id,
                        edge.source_id,
                        edge.subject_name,
                        edge.predicate,
                        edge.object_value,
                        edge.object_type,
                        edge.status,
                    ),
                )
                saved.append(edge)
        return saved

    def save_merge_candidates(
        self,
        candidates: list[ExtractedEntityMergeCandidate],
        timestamp: str,
    ) -> list[EntityMergeCandidate]:
        saved: list[EntityMergeCandidate] = []
        with self.database.connect() as connection:
            for candidate in candidates:
                entity_a_id = self._resolve_entity_id(connection, candidate.entity_a)
                entity_b_id = self._resolve_entity_id(connection, candidate.entity_b)
                if entity_a_id is not None and entity_a_id == entity_b_id:
                    continue
                current_id = entity_merge_candidate_id(
                    entity_a_id or candidate.entity_a,
                    entity_b_id or candidate.entity_b,
                )
                merge_candidate = EntityMergeCandidate(
                    id=current_id,
                    entity_a_id=entity_a_id,
                    entity_b_id=entity_b_id,
                    entity_a_name=candidate.entity_a,
                    entity_b_name=candidate.entity_b,
                    reason=candidate.reason,
                    confidence=candidate.confidence,
                    status="open",
                    created_at=timestamp,
                )
                connection.execute(
                    """
                    INSERT INTO entity_merge_candidates (
                        id, entity_a_id, entity_b_id, entity_a_name,
                        entity_b_name, reason, confidence, status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        reason = excluded.reason,
                        confidence = excluded.confidence,
                        status = excluded.status
                    """,
                    (
                        merge_candidate.id,
                        merge_candidate.entity_a_id,
                        merge_candidate.entity_b_id,
                        merge_candidate.entity_a_name,
                        merge_candidate.entity_b_name,
                        merge_candidate.reason,
                        merge_candidate.confidence,
                        merge_candidate.status,
                        merge_candidate.created_at,
                    ),
                )
                saved.append(merge_candidate)
        return saved

    def save_contradictions(
        self,
        contradictions: list[ExtractedContradiction],
        contexts: list[ClaimGraphContext],
        timestamp: str,
    ) -> list[Contradiction]:
        valid_claim_ids = {context.claim_id for context in contexts}
        saved: list[Contradiction] = []
        with self.database.connect() as connection:
            for contradiction in contradictions:
                if contradiction.relationship == "unrelated":
                    continue
                if (
                    contradiction.claim_a_id not in valid_claim_ids
                    or contradiction.claim_b_id not in valid_claim_ids
                ):
                    continue
                current_id = contradiction_id(
                    contradiction.claim_a_id,
                    contradiction.claim_b_id,
                    contradiction.relationship,
                )
                row = Contradiction(
                    id=current_id,
                    claim_a_id=contradiction.claim_a_id,
                    claim_b_id=contradiction.claim_b_id,
                    relationship=contradiction.relationship,
                    reason=contradiction.reason,
                    confidence=contradiction.confidence,
                    status="open",
                    evidence_ids=contradiction.evidence_ids,
                    created_at=timestamp,
                )
                connection.execute(
                    """
                    INSERT INTO contradictions (
                        id, claim_a_id, claim_b_id, relationship, reason,
                        confidence, status, evidence_ids_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        relationship = excluded.relationship,
                        reason = excluded.reason,
                        confidence = excluded.confidence,
                        status = excluded.status,
                        evidence_ids_json = excluded.evidence_ids_json
                    """,
                    (
                        row.id,
                        row.claim_a_id,
                        row.claim_b_id,
                        row.relationship,
                        row.reason,
                        row.confidence,
                        row.status,
                        json.dumps(row.evidence_ids),
                        row.created_at,
                    ),
                )
                saved.append(row)
        return saved

    def save_entity_page(self, page: WikiPage, entity_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO wiki_pages (
                    id, source_id, path, title, page_type, summary,
                    sha256, created_at, updated_at, frontmatter_json
                )
                VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    title = excluded.title,
                    summary = excluded.summary,
                    sha256 = excluded.sha256,
                    updated_at = excluded.updated_at,
                    frontmatter_json = excluded.frontmatter_json
                """,
                (
                    page.id,
                    str(page.path),
                    page.title,
                    page.page_type,
                    page.summary,
                    page.sha256 or "",
                    page.created_at,
                    page.updated_at,
                    json.dumps({"entity_id": entity_id}),
                ),
            )
            connection.execute("DELETE FROM wiki_pages_fts WHERE id = ?", (page.id,))
            connection.execute(
                """
                INSERT INTO wiki_pages_fts (id, path, title, summary, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (page.id, str(page.path), page.title, page.summary, page.body),
            )

    def search_graph(self, query: str, limit: int = 12) -> GraphSearchResult:
        fts_query = _build_simple_fts_query(query)
        if not fts_query:
            return GraphSearchResult(entities=[], relations=[])
        with self.database.connect() as connection:
            entity_rows = connection.execute(
                """
                SELECT ent.*
                FROM entities_fts
                JOIN entities ent ON ent.id = entities_fts.id
                WHERE entities_fts MATCH ?
                ORDER BY bm25(entities_fts), ent.confidence DESC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
            relation_rows = connection.execute(
                """
                SELECT rel.*
                FROM relation_edges_fts
                JOIN relation_edges rel ON rel.id = relation_edges_fts.id
                WHERE relation_edges_fts MATCH ?
                ORDER BY bm25(relation_edges_fts), rel.confidence DESC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return GraphSearchResult(
            entities=[_row_to_entity(row) for row in entity_rows],
            relations=[_row_to_relation(row) for row in relation_rows],
        )

    def visualize_graph(self, query: str | None = None, limit: int = 50) -> GraphVisualization:
        fts_query = _build_simple_fts_query(query or "")
        with self.database.connect() as connection:
            if fts_query:
                rows = connection.execute(
                    """
                    SELECT rel.*
                    FROM relation_edges_fts
                    JOIN relation_edges rel ON rel.id = relation_edges_fts.id
                    WHERE relation_edges_fts MATCH ?
                    ORDER BY bm25(relation_edges_fts), rel.confidence DESC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM relation_edges
                    ORDER BY confidence DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        relations = [_row_to_relation(row) for row in rows]
        return _relations_to_visualization(relations)

    def get_entity_detail(self, entity_id_or_name: str) -> GraphEntityDetail | None:
        with self.database.connect() as connection:
            entity_id = self._resolve_entity_id(connection, entity_id_or_name)
            if entity_id is None:
                return None
            entity_row = connection.execute(
                "SELECT * FROM entities WHERE id = ?",
                (entity_id,),
            ).fetchone()
            if entity_row is None:
                return None
            outgoing_rows = connection.execute(
                """
                SELECT * FROM relation_edges
                WHERE subject_entity_id = ?
                ORDER BY confidence DESC, predicate ASC
                """,
                (entity_id,),
            ).fetchall()
            incoming_rows = connection.execute(
                """
                SELECT * FROM relation_edges
                WHERE object_entity_id = ?
                ORDER BY confidence DESC, predicate ASC
                """,
                (entity_id,),
            ).fetchall()
            merge_rows = connection.execute(
                """
                SELECT * FROM entity_merge_candidates
                WHERE entity_a_id = ? OR entity_b_id = ?
                ORDER BY confidence DESC
                """,
                (entity_id, entity_id),
            ).fetchall()
            page_row = connection.execute(
                """
                SELECT path FROM wiki_pages
                WHERE page_type = 'entity'
                AND frontmatter_json LIKE ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (f'%"entity_id": "{entity_id}"%',),
            ).fetchone()
        return GraphEntityDetail(
            entity=_row_to_entity(entity_row),
            outgoing_relations=[_row_to_relation(row) for row in outgoing_rows],
            incoming_relations=[_row_to_relation(row) for row in incoming_rows],
            merge_candidates=[_row_to_merge_candidate(row) for row in merge_rows],
            page_path=page_row["path"] if page_row else None,
        )

    def list_contradictions(self, status: str | None = None) -> list[Contradiction]:
        filter_sql = ""
        params: tuple[str, ...] = ()
        if status:
            filter_sql = "WHERE status = ?"
            params = (status,)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM contradictions
                {filter_sql}
                ORDER BY confidence DESC, created_at DESC
                """,
                params,
            ).fetchall()
        return [_row_to_contradiction(row) for row in rows]

    def relation_evidence_ids_for_query(
        self,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("src", "id", source_ids)
        tag_sql, tag_params = _tag_filter_sql("src", tags)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT rel.evidence_id
                FROM relation_edges_fts
                JOIN relation_edges rel ON rel.id = relation_edges_fts.id
                JOIN sources src ON src.id = rel.source_id
                WHERE relation_edges_fts MATCH ?
                {filter_sql}
                {tag_sql}
                ORDER BY bm25(relation_edges_fts), rel.confidence DESC
                LIMIT ?
                """,
                (fts_query, *params, *tag_params, limit),
            ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _resolve_entity_id(self, connection, name: str) -> str | None:
        normalized_name = _normalize_name(name)
        if not normalized_name:
            return None
        row = connection.execute(
            "SELECT id FROM entities WHERE id = ? LIMIT 1",
            (name,),
        ).fetchone()
        if row is not None:
            return row["id"]
        row = connection.execute(
            """
            SELECT entity_id FROM entity_aliases
            WHERE normalized_alias = ?
            ORDER BY confidence DESC
            LIMIT 1
            """,
            (normalized_name,),
        ).fetchone()
        if row is not None:
            return row["entity_id"]
        row = connection.execute(
            """
            SELECT id FROM entities
            WHERE lower(canonical_name) = lower(?)
            ORDER BY confidence DESC
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        return row["id"] if row is not None else None

    def _evidence_by_claim(
        self,
        connection,
        claim_ids: list[str],
    ) -> dict[str, list[ClaimEvidenceContext]]:
        evidence_by_claim: dict[str, list[ClaimEvidenceContext]] = defaultdict(list)
        if not claim_ids:
            return evidence_by_claim
        placeholders = ",".join("?" for _ in claim_ids)
        rows = connection.execute(
            f"""
            SELECT
                ce.claim_id,
                ev.id AS evidence_id,
                ev.locator,
                ev.text,
                ev.summary
            FROM claim_evidence ce
            JOIN evidence_items ev ON ev.id = ce.evidence_id
            WHERE ce.claim_id IN ({placeholders})
            ORDER BY ce.confidence DESC, ev.locator ASC
            """,
            tuple(claim_ids),
        ).fetchall()
        for row in rows:
            evidence_by_claim[row["claim_id"]].append(
                ClaimEvidenceContext(
                    evidence_id=row["evidence_id"],
                    locator=row["locator"],
                    text=row["text"],
                    summary=row["summary"],
                )
            )
        return evidence_by_claim

    def _entities_by_source(self, connection, source_ids: list[str]) -> dict[str, list[str]]:
        entities_by_source: dict[str, list[str]] = defaultdict(list)
        if not source_ids:
            return entities_by_source
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
            entities_by_source[row["source_id"]].append(row["canonical_name"])
        return entities_by_source


def _row_to_entity(row) -> GraphEntity:
    return GraphEntity(
        entity_id=row["id"],
        canonical_name=row["canonical_name"],
        entity_type=row["entity_type"],
        aliases=json.loads(row["aliases_json"]),
        description=row["description"],
        confidence=row["confidence"],
    )


def _row_to_relation(row) -> RelationEdge:
    return RelationEdge(
        id=row["id"],
        subject_entity_id=row["subject_entity_id"],
        subject_name=row["subject_name"],
        predicate=row["predicate"],
        object_entity_id=row["object_entity_id"],
        object_value=row["object_value"],
        object_type=row["object_type"],
        claim_id=row["claim_id"],
        evidence_id=row["evidence_id"],
        source_id=row["source_id"],
        confidence=row["confidence"],
        status=row["status"],
        qualifiers=json.loads(row["qualifiers_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_contradiction(row) -> Contradiction:
    return Contradiction(
        id=row["id"],
        claim_a_id=row["claim_a_id"],
        claim_b_id=row["claim_b_id"],
        relationship=row["relationship"],
        reason=row["reason"],
        confidence=row["confidence"],
        status=row["status"],
        evidence_ids=json.loads(row["evidence_ids_json"]),
        created_at=row["created_at"],
    )


def _row_to_merge_candidate(row) -> EntityMergeCandidate:
    return EntityMergeCandidate(
        id=row["id"],
        entity_a_id=row["entity_a_id"],
        entity_b_id=row["entity_b_id"],
        entity_a_name=row["entity_a_name"],
        entity_b_name=row["entity_b_name"],
        reason=row["reason"],
        confidence=row["confidence"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _relations_to_visualization(relations: list[RelationEdge]) -> GraphVisualization:
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    for relation in relations:
        source_node_id = relation.subject_entity_id or f"subject:{relation.subject_name}"
        target_node_id = relation.object_entity_id or f"literal:{relation.id}"
        nodes[source_node_id] = GraphNode(
            id=source_node_id,
            label=relation.subject_name,
            node_type="entity" if relation.subject_entity_id else "subject",
            confidence=relation.confidence,
        )
        nodes[target_node_id] = GraphNode(
            id=target_node_id,
            label=relation.object_value,
            node_type="entity" if relation.object_entity_id else relation.object_type,
            confidence=relation.confidence,
        )
        edges.append(
            GraphEdge(
                id=relation.id,
                source=source_node_id,
                target=target_node_id,
                label=relation.predicate,
                confidence=relation.confidence,
                claim_id=relation.claim_id,
                evidence_id=relation.evidence_id,
            )
        )
    return GraphVisualization(nodes=list(nodes.values()), edges=edges)


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _build_simple_fts_query(value: str) -> str:
    terms = [
        term
        for term in re.findall(r"[\wÀ-ỹ]+", value.lower())
        if len(term) >= 2
    ]
    return " OR ".join(f'"{term.replace(chr(34), chr(34) + chr(34))}"' for term in terms[:24])


def _source_filter_sql(
    alias: str,
    column: str,
    source_ids: list[str],
) -> tuple[str, list[str]]:
    if not source_ids:
        return "", []
    placeholders = ",".join("?" for _ in source_ids)
    return f"AND {alias}.{column} IN ({placeholders})", list(source_ids)


def _tag_filter_sql(alias: str, tags: list[str]) -> tuple[str, list[str]]:
    if not tags:
        return "", []
    clauses = []
    params = []
    for tag in tags:
        clauses.append(f"{alias}.tags_json LIKE ?")
        params.append(f'%"{tag}"%')
    return "AND (" + " OR ".join(clauses) + ")", params
