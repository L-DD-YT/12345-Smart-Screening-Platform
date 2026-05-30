from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from huxin_platform.db.session import get_db
from huxin_platform.repositories.platform_repository import build_export_file


router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/download")
def export_download_api(
    category: str = Query(default=""),
    risk_level: str = Query(default=""),
    handling_status: str = Query(default=""),
    db: Session = Depends(get_db),
) -> JSONResponse:
    export_result = build_export_file(
        db,
        category=category,
        risk_level=risk_level,
        handling_status=handling_status,
    )
    return JSONResponse(
        {
            "ok": True,
            "message": f"已生成 {export_result['item_count']} 条记录的导出文件。",
            **export_result,
        }
    )
