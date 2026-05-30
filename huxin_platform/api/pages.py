from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from huxin_platform.core.config import settings
from huxin_platform.db.session import get_db
from huxin_platform.services.dashboard_service import DashboardService
from huxin_platform.services.feature_service import FeatureService


def create_page_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()
    dashboard_service = DashboardService()
    feature_service = FeatureService()

    @router.get("/", response_class=HTMLResponse)
    def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        dashboard = dashboard_service.homepage_payload(db)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "dashboard": dashboard,
                "sources": ["12345", "街道综治", "检察业务", "人工补录"],
                "categories": ["民事支持起诉", "行政违法监督", "公益诉讼", "刑事犯罪线索", "其他"],
                "legal_domains": feature_service.list_legal_domains(),
                "risk_levels": ["高", "中", "低"],
                "review_statuses": ["待标注", "已标注", "需复核"],
                "handling_statuses": ["待研判", "待复核", "拟移送", "已办结"],
                "app_config": {
                    "amap_web_key": settings.amap_web_key,
                },
            },
        )

    return router
