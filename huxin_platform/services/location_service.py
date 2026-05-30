from __future__ import annotations

import re
from collections import OrderedDict


class LocationService:
    """Detect and normalize location spans for complaint records."""

    LOCATION_KEYWORDS = (
        "区",
        "镇",
        "街道",
        "社区",
        "村",
        "路",
        "街",
        "巷",
        "号",
        "工地",
        "项目",
        "广场",
        "小区",
        "市场",
        "园区",
        "河道",
        "公园",
        "学校",
        "医院",
    )
    PLACE_TYPE_KEYWORDS = OrderedDict(
        [
            ("市场", ("市场", "商场", "夜市")),
            ("河道", ("河道", "河边", "河岸", "水渠", "沟渠")),
            ("工地", ("工地", "工区", "施工现场")),
            ("项目", ("项目", "工程", "项目部", "安置房")),
            ("小区", ("小区", "社区", "楼栋")),
            ("园区", ("园区", "工业园", "科技园")),
            ("道路", ("道路", "路口", "大街", "胡同", "街巷")),
            ("学校", ("学校", "幼儿园", "中学", "小学")),
            ("医院", ("医院", "卫生院", "诊所")),
            ("公园", ("公园", "绿地", "广场")),
        ]
    )
    LOCATION_NOISE_WORDS = (
        "不详",
        "辖区",
        "范围内",
        "附近",
        "周边",
        "周围",
        "一带",
        "门口",
        "旁边",
        "南侧",
        "北侧",
        "东侧",
        "西侧",
        "长期",
        "存在",
        "问题",
        "投诉",
        "反映",
        "居民",
        "群众",
        "商户",
    )
    DISTRICT_PATTERN = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12}(?:区|县))")
    STREET_PATTERN = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:街道|镇|乡|街|路|巷|村|社区))")
    CORE_PATTERN = re.compile(
        r"([\u4e00-\u9fa5A-Za-z0-9]{2,30}(?:市场|河道|河岸|工地|项目|工程|小区|园区|学校|医院|广场|公园|路口|街区|商圈))"
    )

    def detect_location(self, complaint_text: str, location_text: str | None, district: str | None) -> tuple[bool, str]:
        if location_text:
            return True, location_text.strip()

        district_text = district.strip() if district else ""
        sentences = re.split(r"[，。；\n]", complaint_text)
        for sentence in sentences:
            if any(keyword in sentence for keyword in self.LOCATION_KEYWORDS):
                candidate = sentence.strip()
                if district_text and district_text not in candidate:
                    candidate = f"{district_text}{candidate}"
                return True, candidate[:80]
        return False, district_text

    def normalize_location(self, value: str | None, district: str | None = None) -> str:
        raw = (value or "").strip()
        if not raw and district:
            raw = district.strip()
        normalized = re.sub(r"\s+", "", raw)
        normalized = re.sub(r"[，。；、,.;:：]+", "", normalized)
        return normalized[:80]

    def build_point_profile(self, complaint_text: str, location_text: str | None, district: str | None) -> dict:
        has_location, detected_location = self.detect_location(complaint_text, location_text, district)
        normalized_location = self.normalize_location(detected_location, district)
        district_name = self._extract_first(self.DISTRICT_PATTERN, normalized_location) or (district or "").strip()
        street_name = self._extract_first(self.STREET_PATTERN, normalized_location)
        place_type = self._detect_place_type(normalized_location or complaint_text)
        core_location = self._extract_core_location(normalized_location, complaint_text, district_name, street_name)
        alias_candidates = self._build_alias_candidates(
            normalized_location=normalized_location,
            district_name=district_name,
            street_name=street_name,
            core_location=core_location,
        )
        point_label = self._build_point_label(district_name, street_name, core_location, place_type)
        point_key = self.normalize_location(point_label or normalized_location, district_name)
        point_tokens = self._tokenize_point(point_label or normalized_location)
        return {
            "has_location": has_location,
            "raw_location": detected_location or "",
            "normalized_location": normalized_location,
            "district": district_name,
            "street": street_name,
            "core_location": core_location,
            "place_type": place_type,
            "point_label": point_label,
            "point_key": point_key,
            "alias_candidates": alias_candidates,
            "point_tokens": point_tokens,
        }

    def _extract_core_location(
        self,
        normalized_location: str,
        complaint_text: str,
        district_name: str,
        street_name: str,
    ) -> str:
        for candidate_text in (normalized_location, complaint_text):
            match = self.CORE_PATTERN.search(candidate_text)
            if match:
                return self._clean_core_text(match.group(1), district_name, street_name)
        return self._clean_core_text(normalized_location or complaint_text[:30], district_name, street_name)

    def _build_alias_candidates(
        self,
        *,
        normalized_location: str,
        district_name: str,
        street_name: str,
        core_location: str,
    ) -> list[str]:
        candidates = [
            normalized_location,
            core_location,
            f"{district_name}{core_location}" if district_name and core_location else "",
            f"{street_name}{core_location}" if street_name and core_location else "",
        ]
        seen: list[str] = []
        for item in candidates:
            normalized = self.normalize_location(item)
            if normalized and normalized not in seen:
                seen.append(normalized)
        return seen[:6]

    def _build_point_label(self, district_name: str, street_name: str, core_location: str, place_type: str) -> str:
        parts: list[str] = []
        for part in (district_name, street_name, core_location):
            normalized = self.normalize_location(part)
            if not normalized or normalized == "不详":
                continue
            if any(normalized == self.normalize_location(existing) for existing in parts):
                continue
            parts.append(part)
        if not parts and place_type:
            return place_type
        label = "".join(parts)
        if place_type and place_type not in label:
            label = f"{label}{place_type}"
        return label[:80]

    def _clean_core_text(self, value: str, district_name: str, street_name: str) -> str:
        text = self.normalize_location(value)
        for token in (district_name, street_name):
            normalized = self.normalize_location(token)
            if normalized and text.startswith(normalized):
                text = text[len(normalized) :]
            if normalized and normalized in text:
                text = text.replace(normalized, "", 1)
        for word in self.LOCATION_NOISE_WORDS:
            text = text.replace(word, "")
        text = re.sub(r"(某村主街|某小区及周边|某餐馆门前区域|某写字楼楼道|某农贸市场|某医院西门|某学校门口|某地铁站口)$", r"\1", text)
        return text[:40]

    def _detect_place_type(self, text: str) -> str:
        for label, keywords in self.PLACE_TYPE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return label
        return ""

    def _tokenize_point(self, text: str) -> list[str]:
        normalized = self.normalize_location(text)
        if len(normalized) <= 2:
            return [normalized] if normalized else []
        return [
            normalized[index : index + 2]
            for index in range(0, len(normalized) - 1)
            if normalized[index : index + 2]
        ][:20]

    @staticmethod
    def _extract_first(pattern: re.Pattern[str], text: str) -> str:
        match = pattern.search(text or "")
        return match.group(1).strip() if match else ""
