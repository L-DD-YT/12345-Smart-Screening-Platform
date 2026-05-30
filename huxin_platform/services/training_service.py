from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from huxin_platform.core.config import settings
from huxin_platform.models.entities import HotlineRecord
from huxin_platform.services.feature_service import FeatureService
from huxin_platform.services.model_service import ModelRegistryService


class TrainingService:
    """Train and persist the local machine-learning classifier."""

    def __init__(self) -> None:
        self.feature_service = FeatureService()
        self.model_registry = ModelRegistryService()

    def collect_training_samples(self, db: Session) -> list[dict]:
        query = select(HotlineRecord).where(HotlineRecord.status == "已筛查").order_by(HotlineRecord.id.asc())
        records = db.scalars(query).all()
        samples: list[dict] = []
        for record in records:
            raw_payload = record.raw_payload_json or {}
            external_label = self.feature_service.infer_category_from_external_hints(
                raw_payload.get("成案领域", "") or raw_payload.get("案件领域", ""),
                raw_payload.get("问题分类", "") or raw_payload.get("业务分类", ""),
                record.complaint_text,
            )
            label = external_label or self.feature_service.resolve_training_label(record.manual_label, record.category)
            if not label:
                continue
            if self.feature_service.map_manual_label_to_category(record.manual_label):
                sample_source = "manual"
            elif external_label:
                sample_source = "external_hint"
            else:
                sample_source = "screened"
            samples.append(
                {
                    "record_id": record.id,
                    "text": self.feature_service.build_training_text(
                        record.complaint_text,
                        district=record.district,
                        location_text=record.location_text,
                        matched_rules=record.matched_rules_json or [],
                    ),
                    "label": label,
                    "source": sample_source,
                }
            )
        return samples

    def train_ml_model(self, db: Session) -> dict:
        samples = self.collect_training_samples(db)
        label_counter = Counter(sample["label"] for sample in samples)
        if len(samples) < settings.ml_min_samples:
            raise ValueError(f"可用于训练的样本不足，当前仅 {len(samples)} 条，至少需要 {settings.ml_min_samples} 条。")
        if len(label_counter) < 2:
            raise ValueError("训练样本类别不足，至少需要两个可区分的类别。")

        from joblib import dump
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, classification_report
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline

        texts = [sample["text"] for sample in samples]
        labels = [sample["label"] for sample in samples]
        can_split = len(samples) >= 16 and min(label_counter.values()) >= 2

        if can_split:
            train_x, test_x, train_y, test_y = train_test_split(
                texts,
                labels,
                test_size=0.25,
                random_state=42,
                stratify=labels,
            )
        else:
            train_x, train_y = texts, labels
            test_x, test_y = [], []

        pipeline = Pipeline(
            steps=[
                (
                    "tfidf",
                    TfidfVectorizer(
                        analyzer="char",
                        ngram_range=(2, 5),
                        min_df=1,
                        sublinear_tf=True,
                    ),
                ),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=1500,
                        class_weight="balanced",
                        multi_class="auto",
                    ),
                ),
            ]
        )
        pipeline.fit(train_x, train_y)

        trained_at = datetime.utcnow()
        model_version = f"ml-{trained_at.strftime('%Y%m%d%H%M%S')}"
        metrics = {
            "sample_count": len(samples),
            "label_distribution": dict(label_counter),
            "manual_sample_count": sum(1 for sample in samples if sample["source"] == "manual"),
            "feature_version": self.feature_service.feature_version,
        }
        if test_x:
            predictions = pipeline.predict(test_x)
            metrics["validation_accuracy"] = round(float(accuracy_score(test_y, predictions)), 4)
            metrics["classification_report"] = classification_report(test_y, predictions, output_dict=True, zero_division=0)
        else:
            metrics["validation_accuracy"] = None
            metrics["classification_report"] = {}

        self.model_registry.ensure_directories()
        dump(pipeline, self.model_registry.ml_model_path)
        metadata = {
            "model_name": "tfidf-logreg",
            "model_version": model_version,
            "trained_at": trained_at.isoformat(),
            "sample_count": len(samples),
            "label_distribution": dict(label_counter),
            "feature_version": self.feature_service.feature_version,
            "validation_accuracy": metrics["validation_accuracy"],
        }
        self.model_registry.save_json(self.model_registry.ml_metadata_path, metadata)
        self.model_registry.record_artifact(
            db,
            model_type="ml",
            model_name=metadata["model_name"],
            model_version=model_version,
            file_path=str(self.model_registry.ml_model_path),
            metrics=metrics,
            extra=metadata,
        )
        return {
            "model_name": metadata["model_name"],
            "model_version": model_version,
            "sample_count": len(samples),
            "validation_accuracy": metrics["validation_accuracy"],
            "label_distribution": dict(label_counter),
            "feature_version": self.feature_service.feature_version,
        }
