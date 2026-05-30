from __future__ import annotations

from collections import Counter, defaultdict
from math import sqrt
from typing import Iterable

from huxin_platform.core.config import settings
from huxin_platform.models.entities import HotlineRecord
from huxin_platform.services.inference_service import InferenceService
from huxin_platform.services.location_service import LocationService


class PointAggregationService:
    """Build stable and aggressive supervision point clusters."""

    def __init__(self) -> None:
        self.location_service = LocationService()
        self.inference_service = InferenceService()

    def build_record_point_profile(
        self,
        complaint_text: str,
        location_text: str | None,
        district: str | None,
    ) -> dict:
        profile = self.location_service.build_point_profile(complaint_text, location_text, district)
        stable_key = self._build_stable_key(profile)
        profile["stable_key"] = stable_key
        return profile

    def refresh_clusters(self, records: list[HotlineRecord]) -> dict[str, list[dict]]:
        stable_groups = self._build_stable_groups(records)
        aggressive_groups = self._build_aggressive_groups(records)
        self._apply_cluster_updates(records, stable_groups, aggressive_groups)
        return {
            "stable_clusters": self._serialize_cluster_groups(stable_groups, mode="stable"),
            "aggressive_clusters": self._serialize_cluster_groups(aggressive_groups, mode="aggressive"),
        }

    def build_cluster_payload(self, records: list[HotlineRecord], mode: str = "stable") -> dict:
        normalized_mode = "aggressive" if mode == "aggressive" else "stable"
        if normalized_mode == "aggressive":
            clusters = self._collect_clusters_from_records(records, "aggressive")
            if not clusters:
                clusters = self._serialize_cluster_groups(self._build_aggressive_groups(records), mode="aggressive")
        else:
            clusters = self._collect_clusters_from_records(records, "stable")
            if not clusters:
                clusters = self._serialize_cluster_groups(self._build_stable_groups(records), mode="stable")
        limit = max(1, settings.point_cluster_preview_limit)
        ordered = sorted(clusters, key=lambda item: item["count"], reverse=True)
        return {
            "mode": normalized_mode,
            "items": ordered[:limit],
            "total": len(ordered),
        }

    def _build_stable_groups(self, records: list[HotlineRecord]) -> list[dict]:
        groups: dict[str, list[HotlineRecord]] = defaultdict(list)
        for record in records:
            profile = self._get_profile(record)
            if not profile.get("has_location"):
                continue
            groups[self._build_stable_key(profile)].append(record)

        serialized_groups: list[dict] = []
        for index, (cluster_key, members) in enumerate(
            sorted(groups.items(), key=lambda item: len(item[1]), reverse=True),
            start=1,
        ):
            cluster_id = f"stable-{index:04d}"
            serialized_groups.append(
                self._make_cluster(
                    cluster_id=cluster_id,
                    cluster_key=cluster_key,
                    members=members,
                    mode="stable",
                    confidence=0.96,
                    reason_lines=["区街道与核心点位一致", "采用规范化点位与别名归并"],
                )
            )
        return serialized_groups

    def _build_aggressive_groups(self, records: list[HotlineRecord]) -> list[dict]:
        if not settings.point_aggressive_mode_enabled:
            return []

        candidates = [record for record in records if self._get_profile(record).get("has_location")]
        if not candidates:
            return []

        vectors = self._build_point_vectors(candidates)
        buckets: dict[tuple[str, str], list[HotlineRecord]] = defaultdict(list)
        for record in candidates:
            profile = self._get_profile(record)
            bucket_key = (profile.get("district", ""), profile.get("place_type", ""))
            buckets[bucket_key].append(record)

        clusters: list[dict] = []
        cluster_index = 1
        for bucket_members in buckets.values():
            for member in bucket_members:
                best_cluster = None
                best_score = 0.0
                for cluster in clusters:
                    if cluster["bucket"] != self._cluster_bucket(member):
                        continue
                    score = self._point_similarity(member, cluster["anchor"], vectors)
                    if score > best_score:
                        best_score = score
                        best_cluster = cluster

                if best_cluster and best_score >= settings.point_aggressive_similarity_threshold:
                    best_cluster["members"].append(member)
                    best_cluster["scores"].append(best_score)
                    if best_score > best_cluster["anchor_score"]:
                        best_cluster["anchor"] = member
                        best_cluster["anchor_score"] = best_score
                    continue

                clusters.append(
                    {
                        "id": f"aggressive-{cluster_index:04d}",
                        "bucket": self._cluster_bucket(member),
                        "anchor": member,
                        "anchor_score": 1.0,
                        "members": [member],
                        "scores": [1.0],
                    }
                )
                cluster_index += 1

        results: list[dict] = []
        for cluster in sorted(clusters, key=lambda item: len(item["members"]), reverse=True):
            reasons = self._build_aggressive_reasons(cluster["members"], vectors)
            confidence = round(sum(cluster["scores"]) / len(cluster["scores"]), 4)
            results.append(
                self._make_cluster(
                    cluster_id=cluster["id"],
                    cluster_key=self._build_stable_key(self._get_profile(cluster["anchor"])),
                    members=cluster["members"],
                    mode="aggressive",
                    confidence=confidence,
                    reason_lines=reasons,
                )
            )
        return results

    def _apply_cluster_updates(self, records: list[HotlineRecord], stable_groups: list[dict], aggressive_groups: list[dict]) -> None:
        stable_mapping = {
            member_id: cluster
            for cluster in stable_groups
            for member_id in cluster["member_ids"]
        }
        aggressive_mapping = {
            member_id: cluster
            for cluster in aggressive_groups
            for member_id in cluster["member_ids"]
        }
        for record in records:
            stable_cluster = stable_mapping.get(record.id)
            aggressive_cluster = aggressive_mapping.get(record.id)
            if stable_cluster:
                record.point_cluster_id = stable_cluster["cluster_id"]
                record.point_cluster_label = stable_cluster["label"]
            else:
                record.point_cluster_id = None
                record.point_cluster_label = None
            record.aggressive_cluster_json = aggressive_cluster or {}

    def _serialize_cluster_groups(self, groups: list[dict], mode: str) -> list[dict]:
        return [
            {
                "cluster_id": cluster["cluster_id"],
                "label": cluster["label"],
                "mode": mode,
                "count": cluster["count"],
                "member_ids": cluster["member_ids"],
                "ticket_nos": cluster["ticket_nos"],
                "categories": cluster["categories"],
                "confidence": cluster["confidence"],
                "reason_lines": cluster["reason_lines"],
                "risk_hint": cluster["risk_hint"],
            }
            for cluster in groups
            if cluster["count"] > 1
        ]

    def _collect_clusters_from_records(self, records: list[HotlineRecord], mode: str) -> list[dict]:
        clusters: dict[str, dict] = {}
        for record in records:
            if mode == "aggressive":
                cluster = record.aggressive_cluster_json or {}
                cluster_id = cluster.get("cluster_id")
            else:
                cluster_id = record.point_cluster_id
                cluster = {
                    "cluster_id": record.point_cluster_id,
                    "label": record.point_cluster_label,
                    "confidence": 0.96,
                    "reason_lines": ["区街道与核心点位一致", "采用规范化点位与别名归并"],
                    "risk_hint": "稳健模式，适合直接汇报。",
                }
            if not cluster_id:
                continue
            payload = clusters.setdefault(
                cluster_id,
                {
                    "cluster_id": cluster_id,
                    "label": cluster.get("label") or record.point_cluster_label or "未命名点位",
                    "count": 0,
                    "member_ids": [],
                    "ticket_nos": [],
                    "categories": Counter(),
                    "confidence": cluster.get("confidence", 0.96),
                    "reason_lines": cluster.get("reason_lines", []),
                    "risk_hint": cluster.get("risk_hint", ""),
                },
            )
            payload["count"] += 1
            payload["member_ids"].append(record.id)
            payload["ticket_nos"].append(record.ticket_no)
            if record.category:
                payload["categories"][record.category] += 1

        return [
            {
                **cluster,
                "categories": [label for label, _ in cluster["categories"].most_common(4)],
            }
            for cluster in clusters.values()
            if cluster["count"] > 1
        ]

    def _build_point_vectors(self, records: list[HotlineRecord]) -> dict[int, list[float]]:
        texts: list[str] = []
        targets: list[int] = []
        vectors: dict[int, list[float]] = {}
        for record in records:
            if record.semantic_vector_json:
                vectors[record.id] = [float(value) for value in record.semantic_vector_json]
                continue
            texts.append(self._build_point_text(record))
            targets.append(record.id)

        if texts:
            encoded = self.inference_service.encode_texts(texts)
            for record_id, vector in zip(targets, encoded):
                vectors[record_id] = vector
        return vectors

    def _point_similarity(self, left: HotlineRecord, right: HotlineRecord, vectors: dict[int, list[float]]) -> float:
        left_profile = self._get_profile(left)
        right_profile = self._get_profile(right)
        token_score = self._token_similarity(left_profile.get("point_tokens", []), right_profile.get("point_tokens", []))
        alias_score = self._token_similarity(left_profile.get("alias_candidates", []), right_profile.get("alias_candidates", []))
        vector_score = self._cosine_similarity(vectors.get(left.id, []), vectors.get(right.id, []))
        if left_profile.get("place_type") and right_profile.get("place_type") and left_profile.get("place_type") != right_profile.get("place_type"):
            vector_score *= 0.72
        return round(vector_score * 0.62 + token_score * 0.24 + alias_score * 0.14, 4)

    def _build_aggressive_reasons(self, members: list[HotlineRecord], vectors: dict[int, list[float]]) -> list[str]:
        common_terms = Counter()
        categories = Counter()
        similarities: list[float] = []
        anchor = members[0]
        for member in members:
            profile = self._get_profile(member)
            common_terms.update(profile.get("point_tokens", [])[:6])
            if member.category:
                categories[member.category] += 1
            if member.id != anchor.id:
                similarities.append(self._point_similarity(anchor, member, vectors))

        top_terms = "".join(term for term, _ in common_terms.most_common(4))
        top_categories = "、".join(label for label, _ in categories.most_common(2))
        reason_lines = []
        if top_terms:
            reason_lines.append(f"共同地点词：{top_terms}")
        if top_categories:
            reason_lines.append(f"共同问题类型：{top_categories}")
        if similarities:
            avg_similarity = round(sum(similarities) / len(similarities), 4)
            reason_lines.append(f"平均语义相似度：{avg_similarity}")
        reason_lines.append("增强模式结果仅供研判参考")
        return reason_lines

    def _make_cluster(
        self,
        *,
        cluster_id: str,
        cluster_key: str,
        members: list[HotlineRecord],
        mode: str,
        confidence: float,
        reason_lines: list[str],
    ) -> dict:
        label = self._choose_cluster_label(members)
        categories = Counter(record.category for record in members if record.category)
        unresolved_count = sum(1 for record in members if record.resolved_status == "未解决")
        dissatisfied_count = sum(1 for record in members if record.satisfaction_status == "不满意")
        max_duration = max((record.duration_days or 0) for record in members) if members else 0
        if unresolved_count >= 2 or dissatisfied_count >= 1 or max_duration >= 30:
            risk_hint = f"点位预警：未解决 {unresolved_count} 条，不满意 {dissatisfied_count} 条，最长持续 {max_duration} 天。"
        else:
            risk_hint = (
                "疑似同监督点位，建议人工复核。"
                if mode == "aggressive"
                else "稳健模式，适合直接汇报。"
            )
        return {
            "cluster_id": cluster_id,
            "cluster_key": cluster_key,
            "label": label,
            "count": len(members),
            "member_ids": [record.id for record in members],
            "ticket_nos": [record.ticket_no for record in members],
            "categories": [label for label, _ in categories.most_common(4)],
            "confidence": confidence,
            "reason_lines": reason_lines,
            "risk_hint": risk_hint,
        }

    def _choose_cluster_label(self, members: Iterable[HotlineRecord]) -> str:
        labels = Counter()
        for record in members:
            profile = self._get_profile(record)
            labels.update(
                item
                for item in (
                    profile.get("point_label"),
                    profile.get("core_location"),
                    record.location_text,
                )
                if item
            )
        return labels.most_common(1)[0][0] if labels else "未命名监督点位"

    def _build_stable_key(self, profile: dict) -> str:
        parts = [
            self.location_service.normalize_location(profile.get("district")),
            self.location_service.normalize_location(profile.get("street")),
            self.location_service.normalize_location(profile.get("core_location")),
            self.location_service.normalize_location(profile.get("place_type")),
        ]
        return "|".join(part or "na" for part in parts)

    def _build_point_text(self, record: HotlineRecord) -> str:
        profile = self._get_profile(record)
        return " ".join(
            part
            for part in (
                profile.get("district", ""),
                profile.get("street", ""),
                profile.get("point_label", ""),
                record.title or "",
                record.complaint_text[:120],
            )
            if part
        )

    def _get_profile(self, record: HotlineRecord) -> dict:
        profile = record.normalized_point_json or {}
        if profile:
            return profile
        return self.build_record_point_profile(record.complaint_text, record.location_text, record.district)

    def _cluster_bucket(self, record: HotlineRecord) -> tuple[str, str]:
        profile = self._get_profile(record)
        return (profile.get("district", ""), profile.get("place_type", ""))

    @staticmethod
    def _token_similarity(left: list[str], right: list[str]) -> float:
        left_set = {item for item in left if item}
        right_set = {item for item in right if item}
        if not left_set or not right_set:
            return 0.0
        intersection = len(left_set & right_set)
        union = len(left_set | right_set)
        return round(intersection / union, 4) if union else 0.0

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = sqrt(sum(value * value for value in left))
        right_norm = sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return round(dot / (left_norm * right_norm), 4)
