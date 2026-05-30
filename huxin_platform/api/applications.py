from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from huxin_platform.db.session import get_db
from huxin_platform.repositories.platform_repository import (
    get_record_by_id,
    list_hotline_records,
    serialize_record,
    update_hotline_record_review,
)


router = APIRouter(prefix="/api/ledgers", tags=["ledgers"])


@router.get("")
def ledger_list_api(
    source: str = Query(default=""),
    category: str = Query(default=""),
    risk_level: str = Query(default=""),
    review_status: str = Query(default=""),
    handling_status: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return JSONResponse(
        list_hotline_records(
            db,
            source=source,
            category=category,
            risk_level=risk_level,
            review_status=review_status,
            handling_status=handling_status,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/{record_id}/review")
def review_record_api(
    record_id: int,
    manual_label: str = Form(...),
    review_status: str = Form(...),
    handling_status: str = Form(...),
    review_comment: str = Form(default=""),
    db: Session = Depends(get_db),
) -> JSONResponse:
    record = get_record_by_id(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="未找到需要标注的工单。")

    updated = update_hotline_record_review(
        db,
        record,
        {
            "manual_label": manual_label,
            "review_status": review_status,
            "handling_status": handling_status,
            "review_comment": review_comment or None,
        },
    )
    return JSONResponse(
        {
            "ok": True,
            "message": "线索标注已保存到台账。",
            "item": serialize_record(updated),
        }
    )
