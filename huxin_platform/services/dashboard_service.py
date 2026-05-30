from __future__ import annotations

from sqlalchemy.orm import Session

from huxin_platform.core.config import get_integration_status, get_llm_status
from huxin_platform.repositories.platform_repository import build_dashboard
from huxin_platform.services.inference_service import InferenceService
from huxin_platform.services.integration_service import IntegrationService


class DashboardService:
    """Aggregate homepage and admin data."""

    def __init__(self) -> None:
        self.integration_service = IntegrationService()
        self.inference_service = InferenceService()

    def homepage_payload(
        self,
        db: Session,
        *,
        source: str = "",
        category: str = "",
        legal_domain: str = "",
        risk_level: str = "",
        public_interest_level: str = "",
        warning_level: str = "",
        review_status: str = "",
        handling_status: str = "",
        has_location: str = "",
        is_duplicate: str = "",
        duplicate_level: str = "",
        performance_anomaly_level: str = "",
        priority_level: str = "",
    ) -> dict:
        dashboard = build_dashboard(
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
        dashboard["llm_status"] = get_llm_status()
        dashboard["integration_status"] = get_integration_status()
        dashboard["model_status"] = self.inference_service.get_model_status(db)
        dashboard["integration_sources"] = self.integration_service.list_sources()
        dashboard["push_tasks"] = self.integration_service.list_push_tasks(db, limit=10)
        return dashboard
