from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="SQLite-first multimodal LLM Wiki chatbot API.",
    )
    app.include_router(api_router, prefix="/api")

    @app.get("/", tags=["root"])
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "health": "/api/health",
            "docs": "/docs",
        }

    return app


app = create_app()
