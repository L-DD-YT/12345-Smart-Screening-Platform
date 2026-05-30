from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from huxin_platform.api.admin import router as admin_router
from huxin_platform.api.applications import router as application_router
from huxin_platform.api.assistant import router as assistant_router
from huxin_platform.api.clues import router as clue_router
from huxin_platform.api.documents import router as document_router
from huxin_platform.api.integrations import router as integration_router
from huxin_platform.api.model_admin import router as model_admin_router
from huxin_platform.api.pages import create_page_router
from huxin_platform.db.init_db import init_database


BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
APP_TITLE = "12345市民投诉热线数据中涉检线索智能筛查平台"


def create_app() -> FastAPI:
    app = FastAPI(title=APP_TITLE)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.on_event("startup")
    def startup_event() -> None:
        init_database()

    app.include_router(create_page_router(templates))
    app.include_router(admin_router)
    app.include_router(clue_router)
    app.include_router(assistant_router)
    app.include_router(document_router)
    app.include_router(application_router)
    app.include_router(integration_router)
    app.include_router(model_admin_router)
    return app


app = create_app()
