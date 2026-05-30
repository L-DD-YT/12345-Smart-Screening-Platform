from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from huxin_platform.db.session import get_db
from huxin_platform.repositories.platform_repository import get_record_by_id
from huxin_platform.services.legal_knowledge_service import LegalKnowledgeService
from huxin_platform.services.screening_service import ScreeningService


router = APIRouter(prefix="/api/assistant", tags=["assistant"])
screening_service = ScreeningService()
legal_knowledge_service = LegalKnowledgeService()


def _build_recommended_push_payload(record, judgement: dict) -> dict:
    """Compose a structured push card that downstream business systems can consume directly."""
    return {
        "ticket_no": getattr(record, "ticket_no", ""),
        "title": getattr(record, "title", ""),
        "district": getattr(record, "district", "") or "",
        "legal_domain": getattr(record, "legal_domain", "") or "",
        "domain_confidence": float(getattr(record, "domain_confidence", 0.0) or 0.0),
        "public_interest_level": getattr(record, "public_interest_level", "待复核"),
        "warning_level": getattr(record, "warning_level", "无") or "无",
        "priority_level": getattr(record, "priority_level", "低") or "低",
        "duplicate_level": getattr(record, "duplicate_level", "无") or "无",
        "performance_anomaly_level": getattr(record, "performance_anomaly_level", "无") or "无",
        "prosecution_potential": judgement["prosecution_potential"],
        "investigation_focus": judgement["investigation_focus"],
        "missing_evidence": judgement["evidence_analysis"]["missing_evidence"],
        "primary_statutes": [item["statute_no"] for item in judgement["statutes"][:3]],
        "primary_regulators": [item["regulator"] for item in judgement["regulators"][:3]],
    }


@router.get("/explain/{record_id}")
def explain_api(record_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    record = get_record_by_id(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="未找到对应工单。")
    explain_payload = screening_service.explain_record(record)
    judgement = legal_knowledge_service.build_assistant_judgement(record)
    recommended_push = _build_recommended_push_payload(record, judgement)
    return JSONResponse(
        {
            "ok": True,
            **explain_payload,
            "legal_references": judgement["statutes"],
            "case_references": judgement["cases"],
            "regulator_references": judgement["regulators"],
            "knowledge_snippets": judgement["knowledge_snippets"],
            "investigation_focus": judgement["investigation_focus"],
            "evidence_analysis": judgement["evidence_analysis"],
            "prosecution_potential": judgement["prosecution_potential"],
            "recommended_push": recommended_push,
        }
    )
