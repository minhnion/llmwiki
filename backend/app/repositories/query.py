import json
import re
from collections import defaultdict
from dataclasses import dataclass

from backend.app.domain.query import (
    ArtifactCandidate,
    ArtifactRankingResult,
    EvidenceCandidate,
    EvidenceRankingResult,
    QueryPlan,
    QueryResult,
)
from backend.app.repositories.base import SQLiteRepository


@dataclass(frozen=True)
class ClaimHit:
    id: str
    text: str


class SQLiteQueryRepository(SQLiteRepository):
    def search_evidence(
        self,
        question: str,
        plan: QueryPlan,
        source_ids: list[str],
        tags: list[str],
        max_candidates: int,
    ) -> list[EvidenceCandidate]:
        fts_query = _build_fts_query(question, plan)
        if not fts_query:
            return []

        score_by_id: dict[str, float] = defaultdict(float)
        channels_by_id: dict[str, set[str]] = defaultdict(set)

        with self.database.connect() as connection:
            channel_specs = (
                ("artifact_statement", 4.6, self._search_statement_evidence_ids),
                ("artifact", 4.3, self._search_artifact_evidence_ids),
                ("artifact_relation", 4.1, self._search_artifact_relation_evidence_ids),
                ("evidence", 4.0, self._search_evidence_ids),
                ("claim", 3.0, self._search_claim_evidence_ids),
                ("graph", 2.6, self._search_graph_evidence_ids),
                ("entity", 1.8, self._search_entity_evidence_ids),
                ("wiki_page", 1.4, self._search_page_evidence_ids),
            )
            for channel, weight, search_method in channel_specs:
                rows = search_method(
                    connection,
                    fts_query,
                    source_ids,
                    tags,
                    max_candidates,
                )
                for index, evidence_id in enumerate(_dedupe_ids(rows)):
                    score_by_id[evidence_id] += weight * (max_candidates - index) / max_candidates
                    channels_by_id[evidence_id].add(channel)

            candidates = self._hydrate_candidates(
                connection,
                list(score_by_id.keys()),
                score_by_id,
                channels_by_id,
            )

        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.retrieval_score,
                candidate.confidence,
                len(candidate.claim_ids),
            ),
            reverse=True,
        )[:max_candidates]

    def save_query_result(
        self,
        result: QueryResult,
        ranking: EvidenceRankingResult | ArtifactRankingResult,
        artifact_candidates: list[ArtifactCandidate] | None = None,
        selected_artifact_ids: list[str] | None = None,
    ) -> None:
        artifact_candidates = artifact_candidates or []
        selected_artifact_ids = selected_artifact_ids or []
        selected_artifact_set = set(selected_artifact_ids)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO query_runs (
                    id, question, mode, answer, confidence, candidate_count,
                    selected_evidence_count, created_at, plan_json,
                    ranking_json, result_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.query_id,
                    result.question,
                    result.mode,
                    result.answer,
                    result.confidence,
                    result.candidate_count,
                    len(result.selected_evidence),
                    result.created_at,
                    result.plan.model_dump_json(),
                    ranking.model_dump_json(),
                    result.model_dump_json(),
                ),
            )
            for rank, candidate in enumerate(artifact_candidates, start=1):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO query_candidates (
                        query_id, candidate_id, candidate_type, rank, score,
                        selected, channels_json, payload_json
                    )
                    VALUES (?, ?, 'artifact', ?, ?, ?, ?, ?)
                    """,
                    (
                        result.query_id,
                        candidate.artifact_id,
                        rank,
                        candidate.retrieval_score,
                        1 if candidate.artifact_id in selected_artifact_set else 0,
                        json.dumps(candidate.retrieval_channels),
                        candidate.model_dump_json(),
                    ),
                )
            for citation in result.citations:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO query_citations (
                        query_id, evidence_id, source_id, locator,
                        quote_or_summary, claim_ids_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.query_id,
                        citation.evidence_id,
                        citation.source_id,
                        citation.locator,
                        citation.quote_or_summary,
                        json.dumps(citation.claim_ids),
                    ),
                )

    def _search_evidence_ids(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("s", source_ids, tags)
        rows = connection.execute(
            f"""
            SELECT e.id AS evidence_id
            FROM evidence_items_fts
            JOIN evidence_items e ON e.id = evidence_items_fts.id
            JOIN sources s ON s.id = e.source_id
            WHERE evidence_items_fts MATCH ?
            {filter_sql}
            ORDER BY bm25(evidence_items_fts), e.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, limit),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _search_artifact_evidence_ids(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("s", source_ids, tags)
        rows = connection.execute(
            f"""
            SELECT ae.evidence_id
            FROM artifacts_fts
            JOIN artifacts a ON a.id = artifacts_fts.id
            JOIN artifact_evidence ae ON ae.artifact_id = a.id
            JOIN sources s ON s.id = a.source_id
            WHERE artifacts_fts MATCH ?
            {filter_sql}
            ORDER BY bm25(artifacts_fts), a.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, limit),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _search_statement_evidence_ids(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("s", source_ids, tags)
        rows = connection.execute(
            f"""
            SELECT ase.evidence_id
            FROM artifact_statements_fts
            JOIN artifact_statements ast ON ast.id = artifact_statements_fts.id
            JOIN artifact_statement_evidence ase ON ase.statement_id = ast.id
            JOIN sources s ON s.id = ast.source_id
            WHERE artifact_statements_fts MATCH ?
            {filter_sql}
            ORDER BY bm25(artifact_statements_fts), ast.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, limit),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _search_artifact_relation_evidence_ids(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("s", source_ids, tags)
        rows = connection.execute(
            f"""
            SELECT json_each.value AS evidence_id
            FROM artifact_relations_fts
            JOIN artifact_relations ar ON ar.id = artifact_relations_fts.id
            JOIN artifacts a ON a.id = ar.source_artifact_id
            JOIN sources s ON s.id = a.source_id
            JOIN json_each(ar.evidence_ids_json)
            WHERE artifact_relations_fts MATCH ?
            {filter_sql}
            ORDER BY bm25(artifact_relations_fts), ar.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, limit),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _search_claim_evidence_ids(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("s", source_ids, tags)
        rows = connection.execute(
            f"""
            SELECT ce.evidence_id AS evidence_id
            FROM claims_fts
            JOIN claims c ON c.id = claims_fts.id
            JOIN sources s ON s.id = c.source_id
            JOIN claim_evidence ce ON ce.claim_id = c.id
            WHERE claims_fts MATCH ?
            {filter_sql}
            ORDER BY bm25(claims_fts), c.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, limit),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _search_entity_evidence_ids(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("s", source_ids, tags)
        rows = connection.execute(
            f"""
            SELECT ee.evidence_id
            FROM entities_fts
            JOIN entities ent ON ent.id = entities_fts.id
            JOIN source_entities se ON se.entity_id = ent.id
            JOIN entity_evidence ee
                ON ee.source_id = se.source_id AND ee.entity_id = ent.id
            JOIN sources s ON s.id = se.source_id
            WHERE entities_fts MATCH ?
            {filter_sql}
            ORDER BY bm25(entities_fts), ent.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, limit),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _search_graph_evidence_ids(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("s", source_ids, tags)
        rows = connection.execute(
            f"""
            SELECT rel.evidence_id AS evidence_id
            FROM relation_edges_fts
            JOIN relation_edges rel ON rel.id = relation_edges_fts.id
            JOIN sources s ON s.id = rel.source_id
            WHERE relation_edges_fts MATCH ?
            {filter_sql}
            ORDER BY bm25(relation_edges_fts), rel.confidence DESC
            LIMIT ?
            """,
            (fts_query, *params, limit),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _search_page_evidence_ids(
        self,
        connection,
        fts_query: str,
        source_ids: list[str],
        tags: list[str],
        limit: int,
    ) -> list[str]:
        filter_sql, params = _source_filter_sql("s", source_ids, tags)
        rows = connection.execute(
            f"""
            SELECT ae.evidence_id
            FROM wiki_pages_fts
            JOIN wiki_pages page ON page.id = wiki_pages_fts.id
            JOIN wiki_page_artifacts wpa ON wpa.page_id = page.id
            JOIN artifact_evidence ae ON ae.artifact_id = wpa.artifact_id
            JOIN sources s ON s.id = page.source_id
            WHERE wiki_pages_fts MATCH ?
            {filter_sql}
            ORDER BY bm25(wiki_pages_fts)
            LIMIT ?
            """,
            (fts_query, *params, limit),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def _hydrate_candidates(
        self,
        connection,
        evidence_ids: list[str],
        score_by_id: dict[str, float],
        channels_by_id: dict[str, set[str]],
    ) -> list[EvidenceCandidate]:
        if not evidence_ids:
            return []

        placeholders = ",".join("?" for _ in evidence_ids)
        rows = connection.execute(
            f"""
            SELECT
                ev.id AS evidence_id,
                ev.source_id,
                src.title AS source_title,
                src.original_path AS source_path,
                COALESCE(
                    (
                        SELECT page.path
                        FROM wiki_pages page
                        WHERE page.source_id = ev.source_id
                        ORDER BY CASE WHEN page.page_type = 'source' THEN 0 ELSE 1 END,
                                 page.updated_at DESC
                        LIMIT 1
                    ),
                    ''
                ) AS wiki_page_path,
                ev.locator,
                ev.modality,
                ev.text,
                ev.summary,
                ev.confidence
            FROM evidence_items ev
            JOIN sources src ON src.id = ev.source_id
            WHERE ev.id IN ({placeholders})
            """,
            tuple(evidence_ids),
        ).fetchall()

        claims_by_evidence = self._claims_by_evidence(connection, evidence_ids)
        entities_by_source = self._entities_by_source(
            connection,
            [row["source_id"] for row in rows],
        )

        return [
            EvidenceCandidate(
                evidence_id=row["evidence_id"],
                source_id=row["source_id"],
                source_title=row["source_title"],
                source_path=row["source_path"],
                wiki_page_path=row["wiki_page_path"],
                locator=row["locator"],
                modality=row["modality"],
                text=row["text"],
                summary=row["summary"],
                confidence=row["confidence"],
                claim_ids=[claim.id for claim in claims_by_evidence[row["evidence_id"]]],
                claims=[claim.text for claim in claims_by_evidence[row["evidence_id"]]],
                entities=entities_by_source[row["source_id"]],
                retrieval_score=round(score_by_id[row["evidence_id"]], 4),
                retrieval_channels=sorted(channels_by_id[row["evidence_id"]]),
            )
            for row in rows
        ]

    def _claims_by_evidence(self, connection, evidence_ids: list[str]) -> dict[str, list[ClaimHit]]:
        placeholders = ",".join("?" for _ in evidence_ids)
        rows = connection.execute(
            f"""
            SELECT
                ce.evidence_id,
                c.id AS claim_id,
                c.claim_text
            FROM claim_evidence ce
            JOIN claims c ON c.id = ce.claim_id
            WHERE ce.evidence_id IN ({placeholders})
            ORDER BY c.confidence DESC
            """,
            tuple(evidence_ids),
        ).fetchall()
        claims: dict[str, list[ClaimHit]] = defaultdict(list)
        for row in rows:
            claims[row["evidence_id"]].append(
                ClaimHit(id=row["claim_id"], text=row["claim_text"])
            )
        return claims

    def _entities_by_source(self, connection, source_ids: list[str]) -> dict[str, list[str]]:
        if not source_ids:
            return defaultdict(list)
        unique_source_ids = list(dict.fromkeys(source_ids))
        placeholders = ",".join("?" for _ in unique_source_ids)
        rows = connection.execute(
            f"""
            SELECT
                se.source_id,
                ent.canonical_name
            FROM source_entities se
            JOIN entities ent ON ent.id = se.entity_id
            WHERE se.source_id IN ({placeholders})
            ORDER BY ent.confidence DESC, ent.canonical_name ASC
            """,
            tuple(unique_source_ids),
        ).fetchall()
        entities: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            entities[row["source_id"]].append(row["canonical_name"])
        return entities


def _build_fts_query(question: str, plan: QueryPlan) -> str:
    phrases = [
        question,
        plan.rewritten_question,
        *plan.keywords,
        *plan.entity_hints,
        *plan.subquestions,
        *plan.must_have_evidence,
    ]
    terms: list[str] = []
    for phrase in phrases:
        cleaned_phrase = re.sub(r"\s+", " ", phrase).strip()
        if 1 < len(cleaned_phrase) <= 80:
            terms.append(cleaned_phrase)
        for token in re.findall(r"[\wÀ-ỹ]+", phrase.lower()):
            if len(token) >= 2:
                terms.append(token)

    unique_terms = list(dict.fromkeys(terms))[:32]
    return " OR ".join(f'"{_escape_fts_phrase(term)}"' for term in unique_terms)


def _escape_fts_phrase(term: str) -> str:
    return term.replace('"', '""')


def _source_filter_sql(alias: str, source_ids: list[str], tags: list[str]) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if source_ids:
        placeholders = ",".join("?" for _ in source_ids)
        clauses.append(f"{alias}.id IN ({placeholders})")
        params.extend(source_ids)
    if tags:
        tag_clauses = []
        for tag in tags:
            tag_clauses.append(f"{alias}.tags_json LIKE ?")
            params.append(f'%"{tag}"%')
        clauses.append("(" + " OR ".join(tag_clauses) + ")")
    if not clauses:
        return "", []
    return "AND " + " AND ".join(clauses), params


def _dedupe_ids(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))
