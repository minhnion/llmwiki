from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = Field(default="LLM Wiki Agent", alias="LLM_WIKI_APP_NAME")
    environment: str = Field(default="development", alias="LLM_WIKI_ENV")
    log_level: str = Field(default="INFO", alias="LLM_WIKI_LOG_LEVEL")
    database_path: Path = Field(
        default=PROJECT_ROOT / "data" / "app.sqlite",
        alias="LLM_WIKI_DATABASE_PATH",
    )
    raw_dir: Path = Field(default=PROJECT_ROOT / "raw", alias="LLM_WIKI_RAW_DIR")
    wiki_dir: Path = Field(default=PROJECT_ROOT / "wiki", alias="LLM_WIKI_WIKI_DIR")
    port: int = Field(default=8030, alias="LLM_WIKI_PORT")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="LLM_WIKI_CORS_ORIGINS",
    )
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="LLM_WIKI_MODEL")
    preferred_language: str = Field(default="vi", alias="LLM_WIKI_PREFERRED_LANGUAGE")
    max_file_bytes: int = Field(default=50_000_000, alias="LLM_WIKI_MAX_FILE_BYTES")
    max_output_tokens: int = Field(default=12000, alias="LLM_WIKI_MAX_OUTPUT_TOKENS")
    wiki_search_limit: int = Field(default=12, alias="LLM_WIKI_SEARCH_LIMIT")
    query_source_limit: int = Field(default=3, alias="LLM_WIKI_QUERY_SOURCE_LIMIT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def cors_origin_list(origins: str) -> list[str]:
    return [origin.strip() for origin in origins.split(",") if origin.strip()]
