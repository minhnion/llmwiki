from dataclasses import dataclass

from backend.app.core.config import Settings
from backend.app.db.connection import SQLiteDatabase


@dataclass(frozen=True)
class AppContainer:
    """Small dependency container for wiring application services."""

    settings: Settings
    database: SQLiteDatabase

    @classmethod
    def from_settings(cls, settings: Settings) -> "AppContainer":
        return cls(
            settings=settings,
            database=SQLiteDatabase(settings.database_path),
        )
