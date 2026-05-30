from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from huxin_platform.core.config import get_local_model_paths, settings
from huxin_platform.models.entities import ModelArtifactRecord


class ModelRegistryService:
    """Manage model artifacts and expose runtime status to APIs and UI."""

    def __init__(self) -> None:
        self.paths = get_local_model_paths()

    @property
    def artifacts_dir(self) -> Path:
        return Path(self.paths["artifacts_dir"])

    @property
    def exports_dir(self) -> Path:
        return Path(self.paths["exports_dir"])

    @property
    def ml_model_path(self) -> Path:
        return Path(self.paths["ml_model_path"])

    @property
    def ml_metadata_path(self) -> Path:
        return Path(self.paths["ml_metadata_path"])

    @property
    def semantic_metadata_path(self) -> Path:
        return Path(self.paths["semantic_metadata_path"])

    def ensure_directories(self) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save_json(self, path: Path, payload: dict[str, Any]) -> None:
        self.ensure_directories()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_artifact(
        self,
        db: Session,
        model_type: str,
        model_name: str,
        model_version: str,
        file_path: str,
        metrics: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ModelArtifactRecord:
        db.execute(update(ModelArtifactRecord).where(ModelArtifactRecord.model_type == model_type).values(is_active=False))
        artifact = ModelArtifactRecord(
            model_type=model_type,
            model_name=model_name,
            model_version=model_version,
            file_path=file_path,
            is_active=True,
            metrics_json=metrics or {},
            extra_json=extra or {},
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return artifact

    def get_active_artifact(self, db: Session, model_type: str) -> ModelArtifactRecord | None:
        query = (
            select(ModelArtifactRecord)
            .where(ModelArtifactRecord.model_type == model_type, ModelArtifactRecord.is_active.is_(True))
            .order_by(ModelArtifactRecord.id.desc())
        )
        return db.scalars(query).first()

    def get_status(self, db: Session | None = None) -> dict[str, Any]:
        self.ensure_directories()
        ml_meta = self.load_json(self.ml_metadata_path)
        semantic_meta = self.load_json(self.semantic_metadata_path)
        ml_ready = self.ml_model_path.exists() and bool(ml_meta)
        dl_configured = settings.semantic_model_enabled
        dl_ready = bool(semantic_meta.get("ready"))

        db_ml_version = ""
        db_dl_version = ""
        if db is not None:
            ml_artifact = self.get_active_artifact(db, "ml")
            dl_artifact = self.get_active_artifact(db, "semantic")
            db_ml_version = ml_artifact.model_version if ml_artifact else ""
            db_dl_version = dl_artifact.model_version if dl_artifact else ""

        summary_parts = [
            "ML已就绪" if ml_ready else "ML未训练",
            "DL已预热" if dl_ready else ("DL已配置" if dl_configured else "DL未启用"),
        ]
        detail_parts = []
        if ml_meta.get("model_version") or db_ml_version:
            detail_parts.append(f"ML版本：{ml_meta.get('model_version') or db_ml_version}")
        if semantic_meta.get("model_name") or db_dl_version:
            detail_parts.append(f"DL模型：{semantic_meta.get('model_name') or db_dl_version}")

        return {
            "summary": " / ".join(summary_parts),
            "detail": "；".join(detail_parts) if detail_parts else "当前仍可使用规则引擎独立筛查。",
            "ml_ready": ml_ready,
            "dl_ready": dl_ready,
            "dl_configured": dl_configured,
            "ml_model_name": ml_meta.get("model_name", "tfidf-logreg"),
            "ml_model_version": ml_meta.get("model_version") or db_ml_version or "",
            "dl_model_name": semantic_meta.get("model_name", settings.semantic_model_name),
            "dl_model_version": semantic_meta.get("model_version") or db_dl_version or "",
            "updated_at": ml_meta.get("trained_at") or semantic_meta.get("updated_at") or "",
        }

    def mark_semantic_model_ready(self, db: Session | None, ready: bool, detail: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "ready": ready,
            "model_name": detail.get("model_name", settings.semantic_model_name),
            "model_version": detail.get("model_version", ""),
            "updated_at": datetime.utcnow().isoformat(),
            **detail,
        }
        self.save_json(self.semantic_metadata_path, payload)
        if db is not None and ready:
            self.record_artifact(
                db,
                model_type="semantic",
                model_name=payload["model_name"],
                model_version=payload["model_version"] or payload["model_name"],
                file_path=payload["model_name"],
                metrics={"ready": True},
                extra=payload,
            )
        return payload
