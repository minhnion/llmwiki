import json
from pathlib import Path

from backend.app.core.clock import utc_now_iso
from backend.app.core.ids import (
    claim_id,
    claim_id_from_local,
    entity_id,
    evidence_id,
    evidence_id_from_local,
    review_item_id,
)
from backend.app.domain.extraction import IngestExtractionResult
from backend.app.domain.models import SourceRef, WikiPage
from backend.app.repositories.base import SQLiteRepository


class SQLiteExtractionRepository(SQLiteRepository):
    def save(
        self,
        source: SourceRef,
        extraction: IngestExtractionResult,
        page: WikiPage,
        compiler_run_id: str | None = None,
    ) -> None:
        now = utc_now_iso()
        evidence_by_local_id: dict[str, str] = {}
        evidence_ids_by_locator: dict[str, list[str]] = {}
        claim_ids: list[str] = []

        with self.database.connect() as connection:
            self._delete_source_artifacts(connection, source.id)

            for index, evidence in enumerate(extraction.evidence_items):
                current_evidence_id = (
                    evidence_id_from_local(source.id, evidence.local_id)
                    if evidence.local_id
                    else evidence_id(source.id, evidence.locator, evidence.text, index)
                )
                if evidence.local_id:
                    evidence_by_local_id[evidence.local_id] = current_evidence_id
                evidence_ids_by_locator.setdefault(evidence.locator, []).append(
                    current_evidence_id
                )
                connection.execute(
                    """
                    INSERT INTO evidence_items (
                        id, source_id, local_id, locator, modality, text, summary,
                        confidence, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_evidence_id,
                        source.id,
                        evidence.local_id or None,
                        evidence.locator,
                        evidence.modality,
                        evidence.text,
                        evidence.summary,
                        evidence.confidence,
                        now,
                    ),
                )
                if compiler_run_id:
                    for unit_local_id in evidence.source_unit_ids:
                        connection.execute(
                            """
                            INSERT INTO evidence_source_units (
                                evidence_id, compiler_run_id, source_id, unit_local_id
                            )
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                current_evidence_id,
                                compiler_run_id,
                                source.id,
                                unit_local_id,
                            ),
                        )
                connection.execute(
                    """
                    INSERT INTO evidence_items_fts (id, source_id, locator, text, summary)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        current_evidence_id,
                        source.id,
                        evidence.locator,
                        evidence.text,
                        evidence.summary,
                    ),
                )

            for index, claim in enumerate(extraction.claims):
                current_claim_id = (
                    claim_id_from_local(source.id, claim.local_id)
                    if claim.local_id
                    else claim_id(source.id, claim.text, index)
                )
                claim_ids.append(current_claim_id)
                connection.execute(
                    """
                    INSERT INTO claims (
                        id, source_id, claim_text, normalized_subject,
                        normalized_predicate, normalized_object, status,
                        confidence, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_claim_id,
                        source.id,
                        claim.text,
                        claim.subject,
                        claim.predicate,
                        claim.object,
                        claim.status,
                        claim.confidence,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO claims_fts (
                        id, source_id, claim_text, normalized_subject,
                        normalized_predicate, normalized_object
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_claim_id,
                        source.id,
                        claim.text,
                        claim.subject,
                        claim.predicate,
                        claim.object,
                    ),
                )
                support_ids = [
                    evidence_by_local_id[local_id]
                    for local_id in claim.evidence_local_ids
                    if local_id in evidence_by_local_id
                ]
                if not support_ids:
                    support_ids = [
                        evidence_ids_by_locator[locator][0]
                        for locator in claim.evidence_locators
                        if len(evidence_ids_by_locator.get(locator, [])) == 1
                    ]
                for current_evidence_id in dict.fromkeys(support_ids):
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO claim_evidence (
                            claim_id, evidence_id, support_type, confidence
                        )
                        VALUES (?, ?, 'supports', ?)
                        """,
                        (current_claim_id, current_evidence_id, claim.confidence),
                    )

            for entity in extraction.entities:
                current_entity_id = entity_id(entity.name, entity.entity_type)
                connection.execute(
                    """
                    INSERT INTO entities (
                        id, canonical_name, entity_type, aliases_json,
                        description, confidence, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        aliases_json = excluded.aliases_json,
                        description = excluded.description,
                        confidence = excluded.confidence,
                        updated_at = excluded.updated_at
                    """,
                    (
                        current_entity_id,
                        entity.name,
                        entity.entity_type,
                        json.dumps(entity.aliases),
                        entity.description,
                        entity.confidence,
                        now,
                        now,
                    ),
                )
                support_ids = [
                    evidence_by_local_id[local_id]
                    for local_id in entity.evidence_local_ids
                    if local_id in evidence_by_local_id
                ]
                for current_evidence_id in support_ids:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO entity_evidence (
                            source_id, entity_id, evidence_id
                        )
                        VALUES (?, ?, ?)
                        """,
                        (source.id, current_entity_id, current_evidence_id),
                    )
                if compiler_run_id:
                    for unit_local_id in entity.source_unit_ids:
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO semantic_node_source_units (
                                source_id, entity_id, compiler_run_id, unit_local_id
                            )
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                source.id,
                                current_entity_id,
                                compiler_run_id,
                                unit_local_id,
                            ),
                        )
                connection.execute(
                    "DELETE FROM entities_fts WHERE id = ?",
                    (current_entity_id,),
                )
                connection.execute(
                    """
                    INSERT INTO entities_fts (
                        id, canonical_name, entity_type, aliases, description
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        current_entity_id,
                        entity.name,
                        entity.entity_type,
                        " ".join(entity.aliases),
                        entity.description,
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO source_entities (source_id, entity_id)
                    VALUES (?, ?)
                    """,
                    (source.id, current_entity_id),
                )

            for index, review in enumerate(extraction.review_items):
                connection.execute(
                    """
                    INSERT INTO review_items (
                        id, review_type, title, body, status, source_id, severity, created_at
                    )
                    VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
                    """,
                    (
                        review_item_id(source.id, review.title, review.body, index),
                        review.review_type,
                        review.title,
                        review.body,
                        source.id,
                        review.severity,
                        now,
                    ),
                )

            connection.execute(
                """
                INSERT INTO wiki_pages (
                    id, source_id, path, title, page_type, summary,
                    sha256, created_at, updated_at, frontmatter_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    title = excluded.title,
                    summary = excluded.summary,
                    sha256 = excluded.sha256,
                    updated_at = excluded.updated_at,
                    frontmatter_json = excluded.frontmatter_json
                """,
                (
                    page.id,
                    source.id,
                    str(page.path),
                    page.title,
                    page.page_type,
                    page.summary,
                    page.sha256,
                    page.created_at,
                    page.updated_at,
                    json.dumps(
                        {
                            "source_id": source.id,
                            "source_sha256": source.sha256,
                            "claim_ids": claim_ids,
                        }
                    ),
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
            for current_claim_id in claim_ids:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO page_claims (page_id, claim_id)
                    VALUES (?, ?)
                    """,
                    (page.id, current_claim_id),
                )
            connection.execute(
                """
                UPDATE sources
                SET status = 'ingested', ingested_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, source.id),
            )

    @staticmethod
    def _delete_source_artifacts(connection, source_id: str) -> None:
        page_rows = connection.execute(
            "SELECT id FROM wiki_pages WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        for row in page_rows:
            connection.execute("DELETE FROM wiki_pages_fts WHERE id = ?", (row["id"],))

        evidence_rows = connection.execute(
            "SELECT id FROM evidence_items WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        for row in evidence_rows:
            connection.execute("DELETE FROM evidence_items_fts WHERE id = ?", (row["id"],))

        claim_rows = connection.execute(
            "SELECT id FROM claims WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        for row in claim_rows:
            connection.execute("DELETE FROM claims_fts WHERE id = ?", (row["id"],))

        connection.execute("DELETE FROM review_items WHERE source_id = ?", (source_id,))
        connection.execute("DELETE FROM source_entities WHERE source_id = ?", (source_id,))
        connection.execute("DELETE FROM wiki_pages WHERE source_id = ?", (source_id,))
        connection.execute("DELETE FROM evidence_items WHERE source_id = ?", (source_id,))
        connection.execute("DELETE FROM claims WHERE source_id = ?", (source_id,))


def relative_page_path(wiki_dir: Path, path: Path) -> Path:
    try:
        return path.relative_to(wiki_dir)
    except ValueError:
        return path
