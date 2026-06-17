from backend.app.db.connection import SQLiteDatabase


class SQLiteRepository:
    """Base class for SQLite-backed repositories."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
