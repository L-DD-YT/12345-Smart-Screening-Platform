from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from huxin_platform.db.session import get_db
from huxin_platform.services.dashboard_service import DashboardService


router = APIRouter(prefix="/api", tags=["admin"])
dashboard_service = DashboardService()


@router.get("/dashboard")
def dashboard_api(
    source: str = Query(default=""),
    category: str = Query(default=""),
    legal_domain: str = Query(default=""),
    risk_level: str = Query(default=""),
    public_interest_level: str = Query(default=""),
    warning_level: str = Query(default=""),
    review_status: str = Query(default=""),
    handling_status: str = Query(default=""),
    has_location: str = Query(default=""),
    is_duplicate: str = Query(default=""),
    duplicate_level: str = Query(default=""),
    performance_anomaly_level: str = Query(default=""),
    priority_level: str = Query(default=""),
    db: Session = Depends(get_db),
) -> JSONResponse:
    payload = dashboard_service.homepage_payload(
        db,
        source=source,
        category=category,
        legal_domain=legal_domain,
        risk_level=risk_level,
        public_interest_level=public_interest_level,
        warning_level=warning_level,
        review_status=review_status,
        handling_status=handling_status,
        has_location=has_location,
        is_duplicate=is_duplicate,
        duplicate_level=duplicate_level,
        performance_anomaly_level=performance_anomaly_level,
        priority_level=priority_level,
    )
    return JSONResponse(payload)
