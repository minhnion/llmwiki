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
