from dataclasses import dataclass
from functools import lru_cache

from backend.app.core.config import Settings, get_settings
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


@lru_cache
def get_container() -> AppContainer:
    return AppContainer.from_settings(get_settings())
