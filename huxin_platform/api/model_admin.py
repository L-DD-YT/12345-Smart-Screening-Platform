from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from huxin_platform.db.session import get_db
from huxin_platform.services.inference_service import InferenceService
from huxin_platform.services.training_service import TrainingService


router = APIRouter(prefix="/api/models", tags=["models"])
training_service = TrainingService()
inference_service = InferenceService()


@router.get("/status")
def model_status_api(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(inference_service.get_model_status(db))


@router.post("/train-ml")
def train_ml_model_api(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        result = training_service.train_ml_model(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(
        {
            "ok": True,
            "message": f"本地 ML 模型训练完成，版本 {result['model_version']}。",
            **result,
        }
    )


@router.post("/warmup-dl")
def warmup_dl_model_api(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        result = inference_service.warmup_semantic_model(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(
        {
            "ok": True,
            "message": f"深度语义模型已预热：{result['model_name']}。",
            **result,
        }
    )
