from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from huxin_platform.db.session import get_db
from huxin_platform.schemas.dtos import SyncPullRequest
from huxin_platform.services.integration_service import IntegrationService


router = APIRouter(prefix="/api/integrations", tags=["integrations"])
integration_service = IntegrationService()


@router.get("/sources")
def integration_sources() -> JSONResponse:
    return JSONResponse({"items": integration_service.list_sources()})


@router.post("/pull")
def integration_pull(
    source_system: str = Form(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    payload = SyncPullRequest(source_system=source_system)
    try:
        result = integration_service.pull_source(db, payload.source_system)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"外部来源拉取失败：{exc}") from exc
    return JSONResponse({"ok": True, **result})


@router.get("/push-preview")
def integration_push_preview(
    push_type: str = "daily",
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        result = integration_service.build_push_payload(db, push_type=push_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"推送载荷生成失败：{exc}") from exc
    return JSONResponse({"ok": True, **result})


@router.get("/push/tasks")
def integration_list_push_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return JSONResponse({"items": integration_service.list_push_tasks(db, limit=limit)})


@router.post("/push/enqueue")
def integration_enqueue_push(
    push_type: str = Form(default="daily"),
    trigger_mode: str = Form(default="manual"),
    target_endpoint: str = Form(default=""),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        task = integration_service.enqueue_batch_push(
            db,
            push_type=push_type,
            trigger_mode=trigger_mode,
            target_endpoint=target_endpoint or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"推送任务创建失败：{exc}") from exc
    return JSONResponse({"ok": True, "task": task})


@router.post("/push/emergency")
def integration_emergency_push(
    record_ids: str = Form(...),
    trigger_mode: str = Form(default="manual"),
    target_endpoint: str = Form(default=""),
    db: Session = Depends(get_db),
) -> JSONResponse:
    parsed_ids = [int(item) for item in record_ids.split(",") if item.strip().isdigit()]
    try:
        task = integration_service.enqueue_emergency_push(
            db,
            record_ids=parsed_ids,
            trigger_mode=trigger_mode,
            target_endpoint=target_endpoint or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"紧急推送创建失败：{exc}") from exc
    return JSONResponse({"ok": True, "task": task})


@router.post("/push/deliver")
def integration_deliver_push(
    task_id: int = Form(default=0),
    deliver_pending: bool = Form(default=False),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        if deliver_pending or not task_id:
            tasks = integration_service.deliver_pending_tasks(db)
            return JSONResponse({"ok": True, "items": tasks, "delivered_count": len(tasks)})
        task = integration_service.deliver_push_task(db, task_id)
        return JSONResponse({"ok": True, "task": task})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"推送投递失败：{exc}") from exc
