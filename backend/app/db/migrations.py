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
        name="wiki_agent_foundation",
        sql="""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE sources (
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

        CREATE TABLE source_versions (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE operations (
            id TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            source_id TEXT,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
        );

        CREATE TABLE wiki_pages (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            page_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            body_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE page_sources (
            page_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            PRIMARY KEY (page_id, source_id),
            FOREIGN KEY (page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE evidence_refs (
            id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            locator TEXT NOT NULL,
            quote_or_summary TEXT NOT NULL,
            modality TEXT NOT NULL,
            confidence REAL NOT NULL,
            FOREIGN KEY (page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        );

        CREATE TABLE wiki_links (
            from_page_id TEXT NOT NULL,
            to_page_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (from_page_id, to_page_id),
            FOREIGN KEY (from_page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE,
            FOREIGN KEY (to_page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE
        );

        CREATE TABLE review_items (
            id TEXT PRIMARY KEY,
            review_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            source_id TEXT,
            page_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL,
            FOREIGN KEY (page_id) REFERENCES wiki_pages(id) ON DELETE SET NULL
        );

        CREATE TABLE query_runs (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            mode TEXT NOT NULL,
            answer TEXT NOT NULL,
            confidence TEXT NOT NULL,
            citations_json TEXT NOT NULL DEFAULT '[]',
            pages_read_json TEXT NOT NULL DEFAULT '[]',
            sources_inspected_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE llm_calls (
            id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            estimated_cost REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE wiki_pages_fts USING fts5(
            id UNINDEXED,
            path UNINDEXED,
            title,
            page_type,
            summary,
            body
        );

        CREATE INDEX idx_sources_status ON sources(status);
        CREATE INDEX idx_operations_type_started
            ON operations(operation_type, started_at);
        CREATE INDEX idx_page_sources_source ON page_sources(source_id);
        CREATE INDEX idx_evidence_refs_source ON evidence_refs(source_id);
        CREATE INDEX idx_wiki_links_target ON wiki_links(to_page_id);
        CREATE INDEX idx_review_items_status ON review_items(status);
        CREATE INDEX idx_llm_calls_operation ON llm_calls(operation_id);
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
