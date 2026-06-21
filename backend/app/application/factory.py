from backend.app.application.container import AppContainer
from backend.app.repositories.operations import SQLiteOperationRepository
from backend.app.repositories.queries import SQLiteQueryRepository
from backend.app.repositories.sources import SQLiteSourceRepository
from backend.app.repositories.wiki import SQLiteWikiRepository
from backend.app.services.llm_client import OpenAIWikiAgentClient
from backend.app.services.query_agent import QueryAgentService
from backend.app.services.source_ingest import SourceIngestService
from backend.app.services.wiki_log import WikiLogWriter
from backend.app.services.wiki_store import WikiStore


def build_wiki_store(container: AppContainer) -> WikiStore:
    store = WikiStore(
        wiki_dir=container.settings.wiki_dir,
        repository=SQLiteWikiRepository(container.database),
        source_repository=SQLiteSourceRepository(container.database),
    )
    store.initialize()
    return store


def build_llm_client(container: AppContainer) -> OpenAIWikiAgentClient:
    if not container.settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for Wiki Agent operations.")
    return OpenAIWikiAgentClient(
        api_key=container.settings.openai_api_key,
        model=container.settings.openai_model,
        max_output_tokens=container.settings.max_output_tokens,
        preferred_language=container.settings.preferred_language,
    )


def build_source_ingest(container: AppContainer) -> SourceIngestService:
    return SourceIngestService(
        source_repository=SQLiteSourceRepository(container.database),
        operation_repository=SQLiteOperationRepository(container.database),
        wiki_store=build_wiki_store(container),
        llm_client=build_llm_client(container),
        wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
        max_file_bytes=container.settings.max_file_bytes,
        search_limit=container.settings.wiki_search_limit,
    )


def build_query_agent(container: AppContainer) -> QueryAgentService:
    return QueryAgentService(
        source_repository=SQLiteSourceRepository(container.database),
        query_repository=SQLiteQueryRepository(container.database),
        operation_repository=SQLiteOperationRepository(container.database),
        wiki_store=build_wiki_store(container),
        llm_client=build_llm_client(container),
        wiki_log_writer=WikiLogWriter(container.settings.wiki_dir),
        search_limit=container.settings.wiki_search_limit,
        source_limit=container.settings.query_source_limit,
    )
