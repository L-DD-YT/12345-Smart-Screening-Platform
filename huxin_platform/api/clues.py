from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from huxin_platform.db.session import get_db
from huxin_platform.models.entities import HotlineRecord
from huxin_platform.repositories.platform_repository import (
    build_analysis_payload,
    build_special_report,
    create_hotline_record,
    get_external_sync_record_by_id,
    get_record_by_id,
    import_demo_records,
    import_spreadsheet_records,
    list_hotline_records,
    run_screening,
    serialize_record,
    update_external_sync_record,
)
from huxin_platform.services.point_aggregation_service import PointAggregationService
from huxin_platform.services.semantic_search_service import SemanticSearchService


router = APIRouter(prefix="/api/clues", tags=["clues"])
semantic_search_service = SemanticSearchService()
point_aggregation_service = PointAggregationService()


@router.get("")
def clue_list_api(
    query: str = Query(default=""),
    search_mode: str = Query(default="hybrid"),
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if query.strip():
        payload = semantic_search_service.search_records(
            db,
            query=query,
            search_mode=search_mode,
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
            page=page,
            page_size=page_size,
        )
        return JSONResponse(
            {
                "items": [
                    serialize_record(item, search_explanation=payload["explanations"].get(item.id))
                    for item in payload["items"]
                ],
                "total": payload["total"],
                "page": payload["page"],
                "page_size": payload["page_size"],
                "pages": payload["pages"],
                "search_meta": payload["meta"],
            }
        )

    payload = list_hotline_records(
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
        page=page,
        page_size=page_size,
    )
    return JSONResponse(payload)


@router.get("/analysis")
def clue_analysis_api(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse({"ok": True, **build_analysis_payload(db)})


@router.get("/special-report")
def clue_special_report_api(
    period: str = Query(default="monthly", pattern="^(monthly|quarterly)$"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    payload = build_analysis_payload(db)
    period_report = build_special_report(db, period=period)
    return JSONResponse(
        {
            "ok": True,
            "report": payload["special_report"],
            "difficult_records": payload["difficult_records"],
            "urgent_records": payload.get("urgent_records", []),
            "performance_anomaly_summary": payload.get("performance_anomaly_summary", {}),
            "period_report": period_report,
        }
    )


@router.get("/point-clusters")
def point_cluster_api(
    mode: str = Query(default="stable"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    hydrated_records = db.scalars(select(HotlineRecord).order_by(HotlineRecord.id.desc())).all()
    semantic_search_service.ensure_record_features(db, hydrated_records)
    point_aggregation_service.refresh_clusters(hydrated_records)
    for record in hydrated_records:
        db.add(record)
    db.commit()
    payload = point_aggregation_service.build_cluster_payload(hydrated_records, mode=mode)
    return JSONResponse(payload)


@router.get("/{record_id}")
def clue_detail_api(record_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    record = get_record_by_id(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="未找到对应工单。")
    semantic_search_service.ensure_record_features(db, [record])
    point_aggregation_service.refresh_clusters([record])
    db.add(record)
    db.commit()
    db.refresh(record)
    return JSONResponse({"item": serialize_record(record)})


@router.post("")
def submit_clue(
    ticket_no: str = Form(...),
    source: str = Form(...),
    title: str = Form(...),
    complainant_name: str = Form(default=""),
    complainant_phone: str = Form(default=""),
    district: str = Form(default=""),
    location_text: str = Form(default=""),
    event_time: str = Form(default=""),
    complaint_text: str = Form(...),
    sync_record_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    sync_record = get_external_sync_record_by_id(db, sync_record_id)
    if sync_record and sync_record.linked_record_id:
        raise HTTPException(status_code=409, detail="该外部工单已导入平台，无需重复导入。")

    payload = {
        "ticket_no": ticket_no,
        "source": source,
        "channel": "人工录入" if not sync_record else "外部导入确认",
        "title": title,
        "complainant_name": complainant_name or None,
        "complainant_phone": complainant_phone or None,
        "district": district or None,
        "location_text": location_text or None,
        "event_time": event_time or None,
        "complaint_text": complaint_text,
        "sync_record_id": sync_record_id,
        "raw_payload_json": sync_record.normalized_payload_json if sync_record else None,
    }

    record = create_hotline_record(db, payload)
    if sync_record:
        update_external_sync_record(
            db,
            sync_record,
            {
                "linked_record_id": record.id,
                "sync_status": "已转为平台工单",
                "error_message": None,
            },
        )

    return JSONResponse(
        {
            "ok": True,
            "message": "工单导入成功，已进入待筛查列表。",
            "record_id": record.id,
            "item": serialize_record(record),
        }
    )


@router.post("/import-demo")
def import_demo_api(db: Session = Depends(get_db)) -> JSONResponse:
    created = import_demo_records(db)
    return JSONResponse(
        {
            "ok": True,
            "message": f"已批量导入 {len(created)} 条演示工单。",
            "count": len(created),
        }
    )


@router.post("/import-file")
async def import_file_api(
    source: str = Form(default="12345"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    file_name = file.filename or ""
    if not file_name.lower().endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="仅支持上传 .xls 或 .xlsx 文件。")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空，无法导入。")

    try:
        result = import_spreadsheet_records(db, file_bytes=file_bytes, filename=file_name, source=source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"表格解析失败：{exc}") from exc

    screening_result = {"job_id": None, "screened_count": 0, "model_version": ""}
    if result["record_ids"]:
        screening_result = run_screening(
            db,
            record_ids=result["record_ids"],
            only_pending=False,
        )

    return JSONResponse(
        {
            "ok": True,
            "message": (
                f"文件处理完成：新增 {result['created_count']} 条，"
                f"更新 {result['updated_count']} 条，"
                f"并已自动筛查 {screening_result['screened_count']} 条。"
            ),
            "screening_result": screening_result,
            **result,
        }
    )


@router.post("/run-screening")
def run_screening_api(
    record_ids: str = Form(default=""),
    only_pending: bool = Form(default=True),
    batch_size: int = Form(default=0),
    db: Session = Depends(get_db),
) -> JSONResponse:
    parsed_ids = [int(item) for item in record_ids.split(",") if item.strip().isdigit()]
    result = run_screening(
        db,
        record_ids=parsed_ids or None,
        only_pending=only_pending,
        batch_size=batch_size or None,
    )
    return JSONResponse(
        {
            "ok": True,
            "message": f"已完成 {result['screened_count']} 条工单筛查，批次任务 #{result['job_id']}。",
            **result,
        }
    )
