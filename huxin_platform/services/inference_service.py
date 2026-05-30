from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from huxin_platform.core.config import settings
from huxin_platform.services.feature_service import FeatureService, PROC_CATEGORIES
from huxin_platform.services.model_service import ModelRegistryService


class InferenceService:
    """Fuse rules, local ML classifier, and semantic deep model scores."""

    _ml_bundle: dict[str, Any] | None = None
    _ml_bundle_mtime: float | None = None
    _semantic_bundle: dict[str, Any] | None = None
    _semantic_error: str | None = None

    def __init__(self) -> None:
        self.feature_service = FeatureService()
        self.model_registry = ModelRegistryService()

    def get_runtime_versions(self) -> dict[str, str]:
        ml_meta = self.model_registry.load_json(self.model_registry.ml_metadata_path)
        semantic_meta = self.model_registry.load_json(self.model_registry.semantic_metadata_path)
        return {
            "screening_version": "ensemble-v2",
            "model_version": ml_meta.get("model_version") or semantic_meta.get("model_version") or "rules-v2",
            "feature_version": self.feature_service.feature_version,
        }

    def get_model_status(self, db: Session | None = None) -> dict[str, Any]:
        return self.model_registry.get_status(db)

    def warmup_semantic_model(self, db: Session | None = None) -> dict[str, Any]:
        self._load_semantic_bundle(force_reload=True)
        if self._semantic_bundle is None:
            raise ValueError(self._semantic_error or "深度语义模型加载失败。")
        payload = {
            "model_name": self._semantic_bundle["model_name"],
            "model_version": self._semantic_bundle["model_version"],
            "ready": True,
            "vector_count": len(self._semantic_bundle["prototype_labels"]),
        }
        self.model_registry.mark_semantic_model_ready(db, True, payload)
        return payload

    def semantic_model_available(self) -> bool:
        return self._load_semantic_bundle() is not None

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        bundle = self._load_semantic_bundle()
        if bundle is None or not texts:
            return []
        vectors = self._encode_texts(
            bundle["torch"],
            bundle["tokenizer"],
            bundle["model"],
            bundle["device"],
            texts,
        )
        precision = max(2, settings.semantic_vector_precision)
        return [
            [round(float(value), precision) for value in row]
            for row in vectors.cpu().tolist()
        ]

    def predict(
        self,
        complaint_text: str,
        matched_rules: list[dict] | None = None,
        district: str | None = None,
        location_text: str | None = None,
    ) -> dict[str, Any]:
        rule_scores = self.feature_service.build_rule_scores(complaint_text, matched_rules)
        text_for_model = self.feature_service.build_training_text(
            complaint_text,
            district=district,
            location_text=location_text,
            matched_rules=matched_rules,
        )
        ml_prediction = self._predict_ml(text_for_model)
        dl_prediction = self._predict_semantic(complaint_text)
        ensemble_scores = self._merge_scores(rule_scores, ml_prediction["scores"], dl_prediction["scores"])
        final_category, confidence = max(ensemble_scores.items(), key=lambda item: item[1])
        if confidence < settings.model_confidence_threshold and rule_scores.get(final_category, 0.0) < 0.2:
            final_category = "其他"
            confidence = max(confidence, ensemble_scores.get("其他", 0.0))

        final_subcategory = "模型识别"
        if matched_rules:
            same_category_rules = [item for item in matched_rules if item.get("category") == final_category]
            if same_category_rules:
                final_subcategory = same_category_rules[0].get("subcategory", "规则召回")
        if final_category == "其他":
            final_subcategory = "待人工识别"

        versions = self.get_runtime_versions()
        return {
            "category": final_category,
            "subcategory": final_subcategory,
            "confidence": round(float(confidence), 4),
            "model_version": versions["model_version"],
            "feature_version": versions["feature_version"],
            "ml_prediction_json": ml_prediction,
            "dl_prediction_json": dl_prediction,
            "ensemble_prediction_json": {
                "source": "rules+ml+dl",
                "scores": ensemble_scores,
                "top_candidates": self.feature_service.summarize_top_scores(ensemble_scores, top_k=4),
            },
        }

    def _merge_scores(
        self,
        rule_scores: dict[str, float],
        ml_scores: dict[str, float],
        dl_scores: dict[str, float],
    ) -> dict[str, float]:
        merged: dict[str, float] = {}
        for category in PROC_CATEGORIES:
            merged[category] = round(
                settings.rule_weight * rule_scores.get(category, 0.0)
                + settings.ml_weight * ml_scores.get(category, 0.0)
                + settings.semantic_weight * dl_scores.get(category, 0.0),
                6,
            )
        total = sum(merged.values()) or 1.0
        return {label: round(score / total, 6) for label, score in merged.items()}

    def _predict_ml(self, text: str) -> dict[str, Any]:
        bundle = self._load_ml_bundle()
        if not bundle:
            return {
                "available": False,
                "model_name": "tfidf-logreg",
                "model_version": "",
                "scores": {category: 0.0 for category in PROC_CATEGORIES},
                "top_candidates": [],
            }

        pipeline = bundle["pipeline"]
        classes = list(getattr(pipeline.named_steps["classifier"], "classes_", []))
        probabilities = pipeline.predict_proba([text])[0].tolist()
        score_map = {label: 0.0 for label in PROC_CATEGORIES}
        for label, value in zip(classes, probabilities):
            if label in score_map:
                score_map[label] = round(float(value), 6)
        if sum(score_map.values()) < 1.0:
            score_map["其他"] = round(max(0.0, 1.0 - sum(score_map.values())), 6)
        return {
            "available": True,
            "model_name": bundle["metadata"].get("model_name", "tfidf-logreg"),
            "model_version": bundle["metadata"].get("model_version", ""),
            "scores": score_map,
            "top_candidates": self.feature_service.summarize_top_scores(score_map, top_k=4),
        }

    def _load_ml_bundle(self) -> dict[str, Any] | None:
        model_path = self.model_registry.ml_model_path
        metadata_path = self.model_registry.ml_metadata_path
        if not model_path.exists() or not metadata_path.exists():
            return None

        current_mtime = model_path.stat().st_mtime
        if self.__class__._ml_bundle is not None and self.__class__._ml_bundle_mtime == current_mtime:
            return self.__class__._ml_bundle

        try:
            from joblib import load

            pipeline = load(model_path)
        except Exception:
            return None

        bundle = {
            "pipeline": pipeline,
            "metadata": self.model_registry.load_json(metadata_path),
        }
        self.__class__._ml_bundle = bundle
        self.__class__._ml_bundle_mtime = current_mtime
        return bundle

    def _predict_semantic(self, text: str) -> dict[str, Any]:
        if not settings.semantic_model_enabled:
            return {
                "available": False,
                "model_name": settings.semantic_model_name,
                "model_version": "",
                "scores": {category: 0.0 for category in PROC_CATEGORIES},
                "top_candidates": [],
                "error": "semantic_model_disabled",
            }

        bundle = self._load_semantic_bundle()
        if bundle is None:
            return {
                "available": False,
                "model_name": settings.semantic_model_name,
                "model_version": "",
                "scores": {category: 0.0 for category in PROC_CATEGORIES},
                "top_candidates": [],
                "error": self._semantic_error or "semantic_model_unavailable",
            }

        torch = bundle["torch"]
        tokenizer = bundle["tokenizer"]
        model = bundle["model"]
        device = bundle["device"]
        prototype_labels = bundle["prototype_labels"]
        prototype_vectors = bundle["prototype_vectors"]

        with torch.no_grad():
            encoded = tokenizer(
                [text],
                padding=True,
                truncation=True,
                max_length=settings.semantic_max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            outputs = model(**encoded)
            hidden_state = outputs.last_hidden_state
            attention_mask = encoded["attention_mask"]
            sentence_vector = self._mean_pool(torch, hidden_state, attention_mask)
            sentence_vector = torch.nn.functional.normalize(sentence_vector, p=2, dim=1)
            cosine_scores = torch.matmul(sentence_vector, prototype_vectors.T).squeeze(0)
            probabilities = torch.softmax(cosine_scores, dim=0).cpu().tolist()

        category_scores = {category: 0.0 for category in PROC_CATEGORIES}
        for label, value in zip(prototype_labels, probabilities):
            category_scores[label] = max(category_scores[label], round(float(value), 6))

        normalized_scores = self._normalize_score_map(category_scores)
        return {
            "available": True,
            "model_name": bundle["model_name"],
            "model_version": bundle["model_version"],
            "scores": normalized_scores,
            "top_candidates": self.feature_service.summarize_top_scores(normalized_scores, top_k=4),
        }

    def _load_semantic_bundle(self, force_reload: bool = False) -> dict[str, Any] | None:
        if self.__class__._semantic_bundle is not None and not force_reload:
            return self.__class__._semantic_bundle
        if self.__class__._semantic_error and not force_reload:
            return None

        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:
            self.__class__._semantic_error = f"缺少深度学习依赖：{exc}"
            return None

        model_name = settings.semantic_model_name
        device_name = settings.semantic_model_device
        if device_name == "auto":
            device_name = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModel.from_pretrained(model_name)
            device = torch.device(device_name)
            model.to(device)
            model.eval()
            prototype_labels, prototype_texts = self.feature_service.build_semantic_corpus()
            prototype_vectors = self._encode_texts(torch, tokenizer, model, device, prototype_texts)
        except Exception as exc:
            self.__class__._semantic_error = f"语义模型加载失败：{exc}"
            self.__class__._semantic_bundle = None
            return None

        bundle = {
            "torch": torch,
            "tokenizer": tokenizer,
            "model": model,
            "device": device,
            "prototype_labels": prototype_labels,
            "prototype_vectors": prototype_vectors,
            "model_name": model_name,
            "model_version": f"semantic-{datetime.utcnow().strftime('%Y%m%d')}",
        }
        self.__class__._semantic_bundle = bundle
        self.__class__._semantic_error = None
        return bundle

    def _encode_texts(self, torch, tokenizer, model, device, texts: list[str]):
        all_vectors = []
        with torch.no_grad():
            for batch_start in range(0, len(texts), 8):
                batch_texts = texts[batch_start : batch_start + 8]
                encoded = tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=settings.semantic_max_length,
                    return_tensors="pt",
                )
                encoded = {key: value.to(device) for key, value in encoded.items()}
                outputs = model(**encoded)
                pooled = self._mean_pool(torch, outputs.last_hidden_state, encoded["attention_mask"])
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                all_vectors.append(pooled)
        return torch.cat(all_vectors, dim=0)

    @staticmethod
    def _mean_pool(torch, hidden_state, attention_mask):
        expanded_mask = attention_mask.unsqueeze(-1).expand(hidden_state.size()).float()
        masked = hidden_state * expanded_mask
        summed = masked.sum(dim=1)
        counts = expanded_mask.sum(dim=1).clamp(min=1e-9)
        return summed / counts

    @staticmethod
    def _normalize_score_map(score_map: dict[str, float]) -> dict[str, float]:
        values = list(score_map.values())
        if not any(values):
            return {label: 0.0 for label in score_map}
        total = sum(values) or 1.0
        return {label: round(value / total, 6) for label, value in score_map.items()}
