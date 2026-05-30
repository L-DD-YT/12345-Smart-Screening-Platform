from __future__ import annotations

import hashlib
import re
from collections import Counter

from huxin_platform.services.feature_service import FeatureService
from huxin_platform.services.location_service import LocationService


class DedupService:
    """Build approximate duplicate buckets across people / location / subject / text dimensions."""

    SUBJECT_SUFFIXES = ("公司", "项目部", "项目", "工地", "小区", "市场", "河道", "学校", "园区", "物业", "厂", "中心")

    def __init__(self) -> None:
        self.feature_service = FeatureService()
        self.location_service = LocationService()

    def build_duplicate_key(
        self,
        complaint_text: str,
        location_text: str | None,
        district: str | None,
        complainant_name: str | None = None,
        complainant_phone: str | None = None,
    ) -> str:
        """Composite signature combining location, subject, complainant identity and SimHash bucket."""
        signals = self.build_duplicate_signals(
            complaint_text=complaint_text,
            location_text=location_text,
            district=district,
            complainant_name=complainant_name,
            complainant_phone=complainant_phone,
        )
        return signals["composite_key"]

    def build_duplicate_signals(
        self,
        complaint_text: str,
        location_text: str | None,
        district: str | None,
        complainant_name: str | None = None,
        complainant_phone: str | None = None,
    ) -> dict:
        location_key = self.location_service.normalize_location(location_text, district) or "noloc"
        normalized_text = self.feature_service.normalize_text(complaint_text or "")
        subject_key = self._extract_subject_key(complaint_text or "")
        person_key = self._build_person_key(complainant_name, complainant_phone)
        simhash_bucket = self._simhash_bucket(normalized_text) if normalized_text else "empty"

        composite_key = f"{location_key}|{subject_key}|{simhash_bucket}"
        weak_key = f"{location_key}|{subject_key}"
        cluster_key = f"{location_key}|domain"

        signals = {
            "location_key": location_key,
            "subject_key": subject_key,
            "person_key": person_key,
            "simhash_bucket": simhash_bucket,
            "composite_key": composite_key,
            "weak_key": weak_key,
            "cluster_key": cluster_key,
        }
        return signals

    def classify_duplicate_level(self, *, duplicate_count: int, weak_match_count: int = 0, person_match_count: int = 0) -> tuple[str, list[str]]:
        """Convert raw match counts into 强重复 / 弱重复 / 同区域同类高频 / 无 layers."""
        reasons: list[str] = []
        if duplicate_count >= 3:
            reasons.append(f"同事项重复投诉达到 {duplicate_count} 次")
        elif duplicate_count == 2:
            reasons.append("存在 2 次同事项重复投诉")
        if person_match_count >= 2:
            reasons.append(f"同一投诉人多次反映（{person_match_count} 条）")
        if weak_match_count >= 3 and weak_match_count > duplicate_count:
            reasons.append(f"同区域同类问题高频出现（{weak_match_count} 条）")

        if duplicate_count >= 3 or person_match_count >= 3:
            return "强重复", reasons[:4]
        if duplicate_count == 2 or person_match_count == 2:
            return "弱重复", reasons[:4]
        if weak_match_count >= 3:
            return "同区域同类高频", reasons[:4]
        return "无", reasons[:4] or ["未触发重复投诉条件"]

    def _simhash_bucket(self, normalized_text: str) -> str:
        shingles = self._build_shingles(normalized_text)
        fingerprint = 0
        for bit in range(64):
            weight = 0
            for token, token_weight in shingles.items():
                digest = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                weight += token_weight if (digest >> bit) & 1 else -token_weight
            if weight > 0:
                fingerprint |= 1 << bit
        # Stable prefix bucket so close variants still have a chance to collide.
        return f"{fingerprint:016x}"[:12]

    def _build_shingles(self, normalized_text: str) -> Counter[str]:
        if len(normalized_text) <= 4:
            return Counter({normalized_text: 1})
        tokens = [normalized_text[index : index + 3] for index in range(0, len(normalized_text) - 2)]
        return Counter(tokens)

    @classmethod
    def _extract_subject_key(cls, complaint_text: str) -> str:
        subject_tokens = []
        for suffix in cls.SUBJECT_SUFFIXES:
            if suffix in complaint_text:
                prefix = complaint_text.split(suffix)[0].strip()
                if prefix:
                    candidate = prefix[-12:]
                    subject_tokens.append(f"{candidate}{suffix}")
        if not subject_tokens:
            return "nosubject"
        return hashlib.md5("|".join(subject_tokens[:3]).encode("utf-8")).hexdigest()[:8]

    @staticmethod
    def _build_person_key(complainant_name: str | None, complainant_phone: str | None) -> str:
        normalized_phone = re.sub(r"\D+", "", complainant_phone or "")
        normalized_name = (complainant_name or "").strip()
        if not normalized_phone and not normalized_name:
            return "noperson"
        # Use phone tail + name first/last char to balance privacy with collision risk.
        phone_part = normalized_phone[-4:] if normalized_phone else "0000"
        if normalized_name:
            name_part = f"{normalized_name[0]}{normalized_name[-1]}" if len(normalized_name) >= 2 else normalized_name
        else:
            name_part = "anon"
        return f"{name_part}{phone_part}"
