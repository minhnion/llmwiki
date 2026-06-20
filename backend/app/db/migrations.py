from dataclasses import dataclass

from backend.app.db.connection import SQLiteDatabase


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="initial_source_registry",
        sql="""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL,
            original_path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            mime_type TEXT,
            size_bytes INTEGER NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'registered',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            ingested_at TEXT
        );

        CREATE TABLE IF NOT EXISTS source_versions (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ingest_jobs (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            job_type TEXT NOT NULL DEFAULT 'register',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            error TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sources_sha256 ON sources(sha256);
        CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
        CREATE INDEX IF NOT EXISTS idx_source_versions_source_id ON source_versions(source_id);
        CREATE INDEX IF NOT EXISTS idx_ingest_jobs_source_id ON ingest_jobs(source_id);
        """,
    ),
    Migration(
        version=2,
        name="ingest_extraction_artifacts",
        sql="""
        CREATE TABLE IF NOT EXISTS evidence_items (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            locator TEXT NOT NULL,
            modality TEXT NOT NULL,
            text TEXT NOT NULL,
            summary TEXT NOT NULL,
            confidence REAL NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS claims (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            claim_text TEXT NOT NULL,
            normalized_subject TEXT NOT NULL,
            normalized_predicate TEXT NOT NULL,
            normalized_object TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS claim_evidence (
            claim_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            support_type TEXT NOT NULL DEFAULT 'supports',
            confidence REAL NOT NULL,
            PRIMARY KEY (claim_id, evidence_id),
            FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
            FOREIGN KEY (evidence_id) REFERENCES evidence_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            description TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_entities (
            source_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            PRIMARY KEY (source_id, entity_id),
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS review_items (
            id TEXT PRIMARY KEY,
            review_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            source_id TEXT,
            evidence_id TEXT,
            claim_id TEXT,
            severity TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
            FOREIGN KEY (evidence_id) REFERENCES evidence_items(id) ON DELETE SET NULL,
            FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS wiki_pages (
            id TEXT PRIMARY KEY,
            source_id TEXT,
            path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            page_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            frontmatter_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS page_claims (
            page_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            PRIMARY KEY (page_id, claim_id),
            FOREIGN KEY (page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE,
            FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS evidence_items_fts
        USING fts5(id UNINDEXED, source_id UNINDEXED, locator, text, summary);

        CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts
        USING fts5(
            id UNINDEXED,
            source_id UNINDEXED,
            claim_text,
            normalized_subject,
            normalized_predicate,
            normalized_object
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts
        USING fts5(id UNINDEXED, canonical_name, entity_type, aliases, description);

        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_pages_fts
        USING fts5(id UNINDEXED, path UNINDEXED, title, summary, body);

        CREATE INDEX IF NOT EXISTS idx_evidence_items_source_id ON evidence_items(source_id);
        CREATE INDEX IF NOT EXISTS idx_claims_source_id ON claims(source_id);
        CREATE INDEX IF NOT EXISTS idx_entities_name_type ON entities(canonical_name, entity_type);
        CREATE INDEX IF NOT EXISTS idx_review_items_source_id ON review_items(source_id);
        CREATE INDEX IF NOT EXISTS idx_wiki_pages_source_id ON wiki_pages(source_id);
        """,
    ),
    Migration(
        version=3,
        name="query_runs",
        sql="""
        CREATE TABLE IF NOT EXISTS query_runs (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            mode TEXT NOT NULL,
            answer TEXT NOT NULL,
            confidence TEXT NOT NULL,
            candidate_count INTEGER NOT NULL,
            selected_evidence_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            ranking_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS query_citations (
            query_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            locator TEXT NOT NULL,
            quote_or_summary TEXT NOT NULL,
            claim_ids_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (query_id, evidence_id),
            FOREIGN KEY (query_id) REFERENCES query_runs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_query_runs_created_at ON query_runs(created_at);
        CREATE INDEX IF NOT EXISTS idx_query_citations_source_id ON query_citations(source_id);
        CREATE INDEX IF NOT EXISTS idx_query_citations_evidence_id
        ON query_citations(evidence_id);
        """,
    ),
    Migration(
        version=4,
        name="knowledge_graph",
        sql="""
        CREATE TABLE IF NOT EXISTS graph_runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            claim_count INTEGER NOT NULL DEFAULT 0,
            relation_count INTEGER NOT NULL DEFAULT 0,
            contradiction_count INTEGER NOT NULL DEFAULT 0,
            merge_candidate_count INTEGER NOT NULL DEFAULT 0,
            entity_page_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS entity_aliases (
            entity_id TEXT NOT NULL,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'ingest',
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (entity_id, normalized_alias),
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS relation_edges (
            id TEXT PRIMARY KEY,
            subject_entity_id TEXT,
            subject_name TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_entity_id TEXT,
            object_value TEXT NOT NULL,
            object_type TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL,
            qualifiers_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (subject_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
            FOREIGN KEY (object_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
            FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
            FOREIGN KEY (evidence_id) REFERENCES evidence_items(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS relation_edges_fts
        USING fts5(
            id UNINDEXED,
            source_id UNINDEXED,
            subject_name,
            predicate,
            object_value,
            object_type,
            status
        );

        CREATE TABLE IF NOT EXISTS contradictions (
            id TEXT PRIMARY KEY,
            claim_a_id TEXT NOT NULL,
            claim_b_id TEXT NOT NULL,
            relationship TEXT NOT NULL,
            reason TEXT NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (claim_a_id) REFERENCES claims(id) ON DELETE CASCADE,
            FOREIGN KEY (claim_b_id) REFERENCES claims(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS entity_merge_candidates (
            id TEXT PRIMARY KEY,
            entity_a_id TEXT,
            entity_b_id TEXT,
            entity_a_name TEXT NOT NULL,
            entity_b_name TEXT NOT NULL,
            reason TEXT NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            FOREIGN KEY (entity_a_id) REFERENCES entities(id) ON DELETE SET NULL,
            FOREIGN KEY (entity_b_id) REFERENCES entities(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_relation_edges_subject_entity
        ON relation_edges(subject_entity_id);
        CREATE INDEX IF NOT EXISTS idx_relation_edges_object_entity
        ON relation_edges(object_entity_id);
        CREATE INDEX IF NOT EXISTS idx_relation_edges_claim_id ON relation_edges(claim_id);
        CREATE INDEX IF NOT EXISTS idx_relation_edges_evidence_id ON relation_edges(evidence_id);
        CREATE INDEX IF NOT EXISTS idx_relation_edges_source_id ON relation_edges(source_id);
        CREATE INDEX IF NOT EXISTS idx_contradictions_claim_a ON contradictions(claim_a_id);
        CREATE INDEX IF NOT EXISTS idx_contradictions_claim_b ON contradictions(claim_b_id);
        CREATE INDEX IF NOT EXISTS idx_merge_candidates_entity_a
        ON entity_merge_candidates(entity_a_id);
        CREATE INDEX IF NOT EXISTS idx_merge_candidates_entity_b
        ON entity_merge_candidates(entity_b_id);
        """,
    ),
    Migration(
        version=5,
        name="knowledge_compiler_v2",
        sql="""
        ALTER TABLE sources ADD COLUMN language TEXT;
        ALTER TABLE sources ADD COLUMN compiler_version TEXT;
        ALTER TABLE evidence_items ADD COLUMN local_id TEXT;

        CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_source_local_id
        ON evidence_items(source_id, local_id)
        WHERE local_id IS NOT NULL AND local_id != '';

        CREATE TABLE IF NOT EXISTS compiler_runs (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            status TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            compiler_version TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            model TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            pass_count INTEGER NOT NULL DEFAULT 0,
            coverage_status TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS source_manifests (
            id TEXT PRIMARY KEY,
            compiler_run_id TEXT NOT NULL UNIQUE,
            source_id TEXT NOT NULL,
            language TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS source_units (
            id TEXT PRIMARY KEY,
            compiler_run_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            local_id TEXT NOT NULL,
            label TEXT NOT NULL,
            locator_json TEXT NOT NULL,
            summary TEXT NOT NULL,
            importance REAL NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(compiler_run_id, local_id),
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS compiler_passes (
            id TEXT PRIMARY KEY,
            compiler_run_id TEXT NOT NULL,
            pass_id TEXT NOT NULL,
            iteration INTEGER NOT NULL,
            objective TEXT NOT NULL,
            target_unit_ids_json TEXT NOT NULL DEFAULT '[]',
            expected_outputs_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            result_json TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            UNIQUE(compiler_run_id, pass_id, iteration),
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            local_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            content TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            scope_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL,
            status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '[]',
            compiler_run_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_id, local_id),
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_versions (
            id TEXT PRIMARY KEY,
            artifact_id TEXT NOT NULL,
            compiler_run_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            artifact_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(artifact_id, compiler_run_id),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_evidence (
            artifact_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            confidence REAL NOT NULL,
            PRIMARY KEY (artifact_id, evidence_id),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
            FOREIGN KEY (evidence_id) REFERENCES evidence_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_relations (
            id TEXT PRIMARY KEY,
            source_artifact_id TEXT NOT NULL,
            target_artifact_id TEXT,
            target_literal TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            qualifiers_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL,
            status TEXT NOT NULL,
            compiler_run_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (source_artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
            FOREIGN KEY (target_artifact_id) REFERENCES artifacts(id) ON DELETE SET NULL,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS coverage_reports (
            id TEXT PRIMARY KEY,
            compiler_run_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            iteration INTEGER NOT NULL,
            coverage_status TEXT NOT NULL,
            report_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(compiler_run_id, iteration),
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS artifacts_fts
        USING fts5(
            id UNINDEXED,
            source_id UNINDEXED,
            artifact_type,
            title,
            aliases,
            summary,
            content
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS artifact_relations_fts
        USING fts5(
            id UNINDEXED,
            source_artifact_id UNINDEXED,
            relation_type,
            target_literal
        );

        CREATE INDEX IF NOT EXISTS idx_compiler_runs_source_id
        ON compiler_runs(source_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_compiler_passes_run
        ON compiler_passes(compiler_run_id, iteration);
        CREATE INDEX IF NOT EXISTS idx_source_units_source
        ON source_units(source_id);
        CREATE INDEX IF NOT EXISTS idx_artifacts_source
        ON artifacts(source_id);
        CREATE INDEX IF NOT EXISTS idx_artifacts_type
        ON artifacts(artifact_type);
        CREATE INDEX IF NOT EXISTS idx_artifact_evidence_evidence
        ON artifact_evidence(evidence_id);
        CREATE INDEX IF NOT EXISTS idx_artifact_relations_source
        ON artifact_relations(source_artifact_id);
        CREATE INDEX IF NOT EXISTS idx_artifact_relations_target
        ON artifact_relations(target_artifact_id);
        CREATE INDEX IF NOT EXISTS idx_coverage_reports_source
        ON coverage_reports(source_id, created_at);
        """,
    ),
    Migration(
        version=6,
        name="knowledge_compiler_v3_quality",
        sql="""
        CREATE TABLE IF NOT EXISTS evidence_source_units (
            evidence_id TEXT NOT NULL,
            compiler_run_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            unit_local_id TEXT NOT NULL,
            PRIMARY KEY (evidence_id, compiler_run_id, unit_local_id),
            FOREIGN KEY (evidence_id) REFERENCES evidence_items(id) ON DELETE CASCADE,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_source_units (
            artifact_id TEXT NOT NULL,
            compiler_run_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            unit_local_id TEXT NOT NULL,
            PRIMARY KEY (artifact_id, compiler_run_id, unit_local_id),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_statements (
            id TEXT PRIMARY KEY,
            artifact_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            compiler_run_id TEXT NOT NULL,
            local_id TEXT NOT NULL,
            statement_type TEXT NOT NULL,
            statement_text TEXT NOT NULL,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_value TEXT NOT NULL,
            object_type TEXT NOT NULL,
            source_unit_ids_json TEXT NOT NULL DEFAULT '[]',
            qualifiers_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(artifact_id, local_id),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS compiled_semantic_nodes (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            compiler_run_id TEXT NOT NULL,
            local_id TEXT NOT NULL,
            node_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(source_id, local_id),
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_statement_evidence (
            statement_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            PRIMARY KEY (statement_id, evidence_id),
            FOREIGN KEY (statement_id) REFERENCES artifact_statements(id) ON DELETE CASCADE,
            FOREIGN KEY (evidence_id) REFERENCES evidence_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS entity_evidence (
            source_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            PRIMARY KEY (source_id, entity_id, evidence_id),
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
            FOREIGN KEY (evidence_id) REFERENCES evidence_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS semantic_node_source_units (
            source_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            compiler_run_id TEXT NOT NULL,
            unit_local_id TEXT NOT NULL,
            PRIMARY KEY (source_id, entity_id, compiler_run_id, unit_local_id),
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
            FOREIGN KEY (compiler_run_id) REFERENCES compiler_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS wiki_page_artifacts (
            page_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            PRIMARY KEY (page_id, artifact_id),
            FOREIGN KEY (page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE,
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS wiki_links (
            from_page_id TEXT NOT NULL,
            to_page_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (from_page_id, to_page_id, link_type),
            FOREIGN KEY (from_page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE,
            FOREIGN KEY (to_page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS artifact_statements_fts
        USING fts5(
            id UNINDEXED,
            artifact_id UNINDEXED,
            source_id UNINDEXED,
            statement_type,
            statement_text,
            subject,
            predicate,
            object_value
        );

        CREATE INDEX IF NOT EXISTS idx_evidence_source_units_unit
        ON evidence_source_units(source_id, unit_local_id);
        CREATE INDEX IF NOT EXISTS idx_artifact_source_units_unit
        ON artifact_source_units(source_id, unit_local_id);
        CREATE INDEX IF NOT EXISTS idx_artifact_statements_artifact
        ON artifact_statements(artifact_id);
        CREATE INDEX IF NOT EXISTS idx_artifact_statements_source
        ON artifact_statements(source_id);
        CREATE INDEX IF NOT EXISTS idx_compiled_semantic_nodes_source
        ON compiled_semantic_nodes(source_id);
        CREATE INDEX IF NOT EXISTS idx_entity_evidence_evidence
        ON entity_evidence(evidence_id);
        CREATE INDEX IF NOT EXISTS idx_wiki_page_artifacts_artifact
        ON wiki_page_artifacts(artifact_id);
        """,
    ),
    Migration(
        version=7,
        name="semantic_artifact_retrieval",
        sql="""
        CREATE TABLE IF NOT EXISTS artifact_embeddings (
            id TEXT PRIMARY KEY,
            artifact_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            representation_type TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            vector_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(artifact_id, representation_type, embedding_model),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS knowledge_maps (
            id TEXT PRIMARY KEY,
            map_type TEXT NOT NULL,
            source_scope_json TEXT NOT NULL DEFAULT '[]',
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            map_json TEXT NOT NULL DEFAULT '{}',
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(map_type, source_scope_json)
        );

        CREATE TABLE IF NOT EXISTS knowledge_map_entries (
            id TEXT PRIMARY KEY,
            map_id TEXT NOT NULL,
            parent_entry_id TEXT,
            page_id TEXT,
            artifact_id TEXT,
            entry_type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (map_id) REFERENCES knowledge_maps(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_entry_id) REFERENCES knowledge_map_entries(id)
                ON DELETE CASCADE,
            FOREIGN KEY (page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE,
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS query_candidates (
            query_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            candidate_type TEXT NOT NULL,
            rank INTEGER NOT NULL,
            score REAL NOT NULL,
            selected INTEGER NOT NULL DEFAULT 0,
            channels_json TEXT NOT NULL DEFAULT '[]',
            payload_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (query_id, candidate_id, candidate_type),
            FOREIGN KEY (query_id) REFERENCES query_runs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_artifact_embeddings_artifact
        ON artifact_embeddings(artifact_id);
        CREATE INDEX IF NOT EXISTS idx_artifact_embeddings_source_model
        ON artifact_embeddings(source_id, embedding_model);
        CREATE INDEX IF NOT EXISTS idx_artifact_embeddings_model_type
        ON artifact_embeddings(embedding_model, representation_type);
        CREATE INDEX IF NOT EXISTS idx_knowledge_map_entries_map
        ON knowledge_map_entries(map_id);
        CREATE INDEX IF NOT EXISTS idx_knowledge_map_entries_artifact
        ON knowledge_map_entries(artifact_id);
        CREATE INDEX IF NOT EXISTS idx_knowledge_map_entries_page
        ON knowledge_map_entries(page_id);
        CREATE INDEX IF NOT EXISTS idx_query_candidates_query
        ON query_candidates(query_id, rank);
        """,
    ),
)


class MigrationRunner:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def run(self) -> list[Migration]:
        applied: list[Migration] = []
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            existing = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in MIGRATIONS:
                if migration.version in existing:
                    continue
                connection.executescript(migration.sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
                applied.append(migration)
        return applied
