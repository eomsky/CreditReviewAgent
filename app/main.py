"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.database.poc_store import initialize_database


def create_app() -> FastAPI:
    initialize_database(seed=settings.POC_AUTO_SEED)
    application = FastAPI(title=settings.PROJECT_NAME)
    application.include_router(api_router, prefix="/api/v1")

    web_dir = Path(__file__).resolve().parent / "web"
    application.mount("/static", StaticFiles(directory=web_dir), name="static")

    @application.get("/", include_in_schema=False)
    async def web_app() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    return application


app = create_app()
