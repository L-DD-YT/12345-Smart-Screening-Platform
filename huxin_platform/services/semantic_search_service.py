from __future__ import annotations

from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from huxin_platform.core.config import settings
from huxin_platform.models.entities import HotlineRecord
from huxin_platform.services.feature_service import CATEGORY_KEYWORDS, PROC_CATEGORIES
from huxin_platform.services.inference_service import InferenceService
from huxin_platform.services.point_aggregation_service import PointAggregationService


class SemanticSearchService:
    """Hybrid semantic retrieval with explainable scoring."""

    QUERY_EXPANSIONS = {
        "监督检查履职": [
            "监管不到位",
            "履职不力",
            "长期未整改",
            "多次投诉未处理",
            "执法不规范",
            "现场核查并督促整改",
            "请属地联合行业主管部门依法处理",
            "核实责任主体",
            "加强巡查与执法",
            "建立长效机制",
            "请承办单位电话告知处理结果",
            "避免反弹",
        ],
        "监管不到位": [
            "监督检查履职",
            "长期未整改",
            "反复投诉",
            "未及时处理",
            "现场核查并督促整改",
            "行业主管部门",
            "核实责任主体",
        ],
        "公益诉讼": [
            "环境污染",
            "公共安全",
            "河道污染",
            "垃圾堆放",
            "油烟扰民",
            "消防通道",
            "公益诉讼（生态环境）",
            "公益诉讼（消费者权益）",
            "公益诉讼（控烟）",
            "公益诉讼（文物和文化遗产）",
            "公益诉讼（单用途预付卡）",
            "农贸市场",
            "公园公厕",
            "景区入口沿线",
            "施工噪声",
            "吸烟问题",
        ],
        "行政监督": ["小过重罚", "同案不同罚", "重复处罚", "程序违法", "执法不规范"],
        "点位": ["同一地点", "同一位置", "同一场所", "同一监督点位", "相同点位"],
        "环境污染": ["污水", "垃圾堆放", "油烟扰民", "黑臭水体", "异味", "河道污染"],
        "同点位反复投诉": [
            "反复投诉",
            "重复投诉",
            "多次投诉",
            "已多次与现场人员沟通未果",
            "投诉集中",
            "通过热线反映",
            "避免反弹",
            "加强巡查与执法",
            "同类问题开展排查",
        ],
        "反复投诉": [
            "同点位反复投诉",
            "重复投诉",
            "多次投诉",
            "已多次与现场人员沟通未果",
            "投诉集中",
        ],
    }
    GOVERNANCE_PHRASES = (
        "已多次与现场人员沟通未果",
        "请属地联合行业主管部门依法处理",
        "现场核查并督促整改",
        "请承办单位电话告知处理结果",
        "避免反弹",
        "核实责任主体",
        "依法依规处理",
        "加强巡查与执法",
        "建立长效机制",
        "通过热线反映",
        "投诉集中",
    )
    PUBLIC_INTEREST_TERMS = (
        "公益诉讼（生态环境）",
        "公益诉讼（消费者权益）",
        "公益诉讼（控烟）",
        "公益诉讼（文物和文化遗产）",
        "公益诉讼（单用途预付卡）",
        "施工噪声",
        "电梯故障",
        "吸烟问题",
        "控烟管理",
        "道路破损",
        "文物保护",
        "公共环境",
    )
    REPEAT_TERMS = (
        "已多次与现场人员沟通未果",
        "多次投诉",
        "重复投诉",
        "反复投诉",
        "投诉集中",
        "避免反弹",
        "同类问题开展排查",
    )

    def __init__(self) -> None:
        self.inference_service = InferenceService()
        self.point_service = PointAggregationService()

    def ensure_record_features(self, db: Session, records: list[HotlineRecord]) -> None:
        dirty_records: list[HotlineRecord] = []
        missing_vectors: list[HotlineRecord] = []
        for record in records:
            needs_profile_refresh = self._should_refresh_point_profile(record.normalized_point_json or {})
            profile = (
                self.point_service.build_record_point_profile(
                    record.complaint_text,
                    record.location_text,
                    record.district,
                )
                if needs_profile_refresh or not record.normalized_point_json
                else record.normalized_point_json
            )
            needs_keyword_refresh = self._should_refresh_semantic_keywords(record.semantic_keywords_json or {})
            keywords = (
                self._build_semantic_keywords(record, profile)
                if needs_keyword_refresh or not record.semantic_keywords_json
                else record.semantic_keywords_json
            )
            if needs_profile_refresh or not record.normalized_point_json:
                record.normalized_point_json = profile
                dirty_records.append(record)
            if needs_keyword_refresh or not record.semantic_keywords_json:
                record.semantic_keywords_json = keywords
                if record not in dirty_records:
                    dirty_records.append(record)
            if not record.semantic_vector_json or needs_profile_refresh or needs_keyword_refresh:
                missing_vectors.append(record)

        if missing_vectors:
            texts = [
                self._build_semantic_text(record, record.normalized_point_json or {})
                for record in missing_vectors
            ]
            vectors = self.inference_service.encode_texts(texts)
            for record, vector in zip(missing_vectors, vectors):
                record.semantic_vector_json = vector
                if record not in dirty_records:
                    dirty_records.append(record)

        if dirty_records:
            for record in dirty_records:
                db.add(record)
            db.commit()
            for record in dirty_records:
                db.refresh(record)

    @staticmethod
    def _should_refresh_point_profile(profile: dict) -> bool:
        if not profile:
            return True
        point_label = str(profile.get("point_label", "") or "")
        return "不详" in point_label or point_label.count("房山区") > 1

    @staticmethod
    def _should_refresh_semantic_keywords(keywords: dict) -> bool:
        if not keywords:
            return True
        return (
            not keywords.get("case_domain")
            or "governance_terms" not in keywords
            or "repeat_terms" not in keywords
            or "legal_domain" not in keywords
            or "public_interest_level" not in keywords
            or "warning_flags" not in keywords
        )

    def search_records(
        self,
        db: Session,
        *,
        query: str,
        search_mode: str = "hybrid",
        source: str = "",
        category: str = "",
        legal_domain: str = "",
        risk_level: str = "",
        public_interest_level: str = "",
        warning_level: str = "",
        review_status: str = "",
        handling_status: str = "",
        has_location: str = "",
        is_duplicate: str = "",
        duplicate_level: str = "",
        performance_anomaly_level: str = "",
        priority_level: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 1, "meta": {}}

        records = self._load_filtered_records(
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
        )
        self.ensure_record_features(db, records)

        expanded_terms = self._expand_query(normalized_query)
        query_vector = self._encode_query(normalized_query, search_mode)
        category_preferences = self._resolve_query_categories(expanded_terms)
        query_profile = self._build_query_profile(normalized_query, expanded_terms)

        ranked_items = []
        for record in records:
            score_payload = self._score_record(
                record=record,
                query=normalized_query,
                expanded_terms=expanded_terms,
                query_vector=query_vector,
                search_mode=search_mode,
                category_preferences=category_preferences,
                query_profile=query_profile,
            )
            if score_payload["total_score"] <= 0:
                continue
            ranked_items.append(score_payload)

        ranked_items.sort(key=lambda item: item["total_score"], reverse=True)
        safe_page = max(page, 1)
        safe_page_size = min(max(page_size, 1), settings.max_query_page_size)
        total = len(ranked_items)
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        page_items = ranked_items[start:end]
        pages = max(1, (total + safe_page_size - 1) // safe_page_size) if total else 1
        return {
            "items": [item["record"] for item in page_items],
            "explanations": {item["record"].id: item["explanation"] for item in page_items},
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "pages": pages,
            "meta": {
                "query": normalized_query,
                "search_mode": search_mode,
                "expanded_terms": expanded_terms,
                "semantic_enabled": bool(query_vector),
                "candidate_count": len(records),
                "matched_count": total,
                "query_profile": query_profile,
            },
        }

    def _load_filtered_records(
        self,
        db: Session,
        *,
        source: str,
        category: str,
        legal_domain: str,
        risk_level: str,
        public_interest_level: str = "",
        warning_level: str = "",
        review_status: str,
        handling_status: str,
        has_location: str,
        is_duplicate: str,
        duplicate_level: str = "",
        performance_anomaly_level: str = "",
        priority_level: str = "",
    ) -> list[HotlineRecord]:
        query = select(HotlineRecord)
        if source:
            query = query.where(HotlineRecord.source == source)
        if category:
            query = query.where(HotlineRecord.category == category)
        if legal_domain:
            query = query.where(HotlineRecord.public_interest_level == "公益", HotlineRecord.legal_domain == legal_domain)
        if risk_level:
            query = query.where(HotlineRecord.risk_level == risk_level)
        if public_interest_level:
            query = query.where(HotlineRecord.public_interest_level == public_interest_level)
        if warning_level:
            query = query.where(HotlineRecord.warning_level == warning_level)
        if review_status:
            query = query.where(HotlineRecord.review_status == review_status)
        if handling_status:
            query = query.where(HotlineRecord.handling_status == handling_status)
        if has_location == "true":
            query = query.where(HotlineRecord.has_location.is_(True))
        elif has_location == "false":
            query = query.where(HotlineRecord.has_location.is_(False))
        if is_duplicate == "true":
            query = query.where(HotlineRecord.is_duplicate.is_(True))
        elif is_duplicate == "false":
            query = query.where(HotlineRecord.is_duplicate.is_(False))
        if duplicate_level:
            query = query.where(HotlineRecord.duplicate_level == duplicate_level)
        if performance_anomaly_level:
            query = query.where(HotlineRecord.performance_anomaly_level == performance_anomaly_level)
        if priority_level:
            query = query.where(HotlineRecord.priority_level == priority_level)
        return db.scalars(query.order_by(HotlineRecord.id.desc())).all()

    def _build_semantic_keywords(self, record: HotlineRecord, point_profile: dict) -> dict:
        raw_payload = record.raw_payload_json or {}
        case_domain = str(raw_payload.get("成案领域", "") or raw_payload.get("案件领域", "") or "")
        issue_category = str(raw_payload.get("问题分类", "") or raw_payload.get("业务分类", "") or "")
        text = " ".join(
            filter(
                None,
                [
                    record.title,
                    record.complaint_text,
                    record.category,
                    point_profile.get("point_label", ""),
                    case_domain,
                    issue_category,
                ],
            )
        )
        matched_terms = []
        category_terms = []
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                category_terms.append(category)
                matched_terms.extend(keyword for keyword in keywords if keyword in text)
        governance_terms = [phrase for phrase in self.GOVERNANCE_PHRASES if phrase in text]
        public_interest_terms = [phrase for phrase in self.PUBLIC_INTEREST_TERMS if phrase in text or phrase == case_domain]
        repeat_terms = [phrase for phrase in self.REPEAT_TERMS if phrase in text]
        aliases = point_profile.get("alias_candidates", [])
        place_type = point_profile.get("place_type", "")
        return {
            "matched_terms": sorted(set(matched_terms + governance_terms + public_interest_terms + repeat_terms))[:30],
            "category_terms": sorted(set(category_terms)),
            "aliases": aliases,
            "place_type": place_type,
            "point_label": point_profile.get("point_label", ""),
            "case_domain": case_domain,
            "issue_category": issue_category,
            "legal_domain": record.legal_domain if record.public_interest_level != "私益" else "",
            "public_interest_level": record.public_interest_level,
            "governance_terms": governance_terms[:10],
            "repeat_terms": repeat_terms[:10],
            "warning_flags": (record.warning_flags_json or [])[:10],
        }

    def _build_semantic_text(self, record: HotlineRecord, point_profile: dict) -> str:
        return " [SEP] ".join(
            part
            for part in (
                record.title or "",
                record.category or "",
                point_profile.get("point_label", ""),
                " ".join(point_profile.get("alias_candidates", [])),
                (record.semantic_keywords_json or {}).get("case_domain", ""),
                (record.semantic_keywords_json or {}).get("issue_category", ""),
                record.legal_domain if record.public_interest_level != "私益" else "",
                record.public_interest_level,
                " ".join(record.warning_flags_json or []),
                record.complaint_text or "",
            )
            if part
        )

    def _expand_query(self, query: str) -> list[str]:
        expansions = {query}
        for seed, related_terms in self.QUERY_EXPANSIONS.items():
            if seed in query or query in seed:
                expansions.update(related_terms)
        for category, keywords in CATEGORY_KEYWORDS.items():
            if category in query or any(keyword in query for keyword in keywords):
                expansions.update(keywords)
                expansions.add(category)
        return sorted(expansions, key=len, reverse=True)[:16]

    def _resolve_query_categories(self, expanded_terms: list[str]) -> set[str]:
        matched_categories = set()
        for category in PROC_CATEGORIES:
            if category in expanded_terms:
                matched_categories.add(category)
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(term in keywords for term in expanded_terms):
                matched_categories.add(category)
        return matched_categories

    def _build_query_profile(self, query: str, expanded_terms: list[str]) -> dict:
        joined = " ".join(expanded_terms + [query])
        return {
            "is_supervision": any(token in joined for token in ("监督", "履职", "监管", "整改", "巡查", "执法")),
            "is_public_interest": "公益诉讼" in joined or any(token in joined for token in ("生态环境", "控烟", "消费者权益", "文物保护", "公共利益")),
            "is_repeat_point": any(token in joined for token in ("反复投诉", "重复投诉", "多次投诉", "同点位", "未解决")),
        }

    def _encode_query(self, query: str, search_mode: str) -> list[float]:
        if search_mode not in {"semantic", "hybrid"} or not settings.semantic_search_enabled:
            return []
        vectors = self.inference_service.encode_texts([query])
        return vectors[0] if vectors else []

    def _score_record(
        self,
        *,
        record: HotlineRecord,
        query: str,
        expanded_terms: list[str],
        query_vector: list[float],
        search_mode: str,
        category_preferences: set[str],
        query_profile: dict,
    ) -> dict:
        keywords = record.semantic_keywords_json or {}
        point_profile = record.normalized_point_json or {}
        text_blob = "\n".join(
            filter(
                None,
                [
                    record.title,
                    record.complaint_text,
                    record.category,
                    record.location_text,
                    point_profile.get("point_label", ""),
                    keywords.get("case_domain", ""),
                    keywords.get("issue_category", ""),
                    " ".join(keywords.get("matched_terms", [])),
                    " ".join(keywords.get("aliases", [])),
                    " ".join(keywords.get("governance_terms", [])),
                    " ".join(keywords.get("repeat_terms", [])),
                    keywords.get("legal_domain", ""),
                    keywords.get("public_interest_level", ""),
                    " ".join(keywords.get("warning_flags", [])),
                ],
            )
        )

        keyword_hits = [term for term in expanded_terms if term and term in text_blob]
        keyword_score = min(1.0, 0.32 + len(keyword_hits) * 0.12) if query in text_blob else min(0.66, len(keyword_hits) * 0.09)
        expansion_score = min(1.0, len([term for term in keyword_hits if term != query]) * 0.12)
        semantic_score = self._cosine_similarity(query_vector, [float(value) for value in (record.semantic_vector_json or [])])
        category_boost = 0.08 if record.category in category_preferences else 0.0
        location_boost = 0.06 if record.has_location else 0.0
        supervision_boost = self._score_supervision_intent(query_profile, keywords, text_blob)
        public_interest_boost = self._score_public_interest_intent(query_profile, keywords, record)
        repeat_point_boost = self._score_repeat_point_intent(query_profile, record, text_blob)

        if search_mode == "keyword":
            total_score = keyword_score + expansion_score * 0.4 + category_boost + supervision_boost + public_interest_boost + repeat_point_boost
        elif search_mode == "semantic":
            total_score = semantic_score + category_boost + location_boost * 0.4 + supervision_boost + public_interest_boost + repeat_point_boost
        else:
            total_score = (
                keyword_score * 0.40
                + expansion_score * 0.16
                + semantic_score * 0.28
                + category_boost
                + location_boost * 0.08
                + supervision_boost
                + public_interest_boost
                + repeat_point_boost
            )

        cluster_member_count = self._cluster_member_count(record)
        supervision_match = (
            not query_profile.get("is_supervision")
            or bool(keyword_hits)
            or (
                supervision_boost > 0
                and (
                    "行政检察" in keywords.get("case_domain", "")
                    or "公益诉讼" in keywords.get("case_domain", "")
                    or record.category in {"行政违法监督", "公益诉讼"}
                )
            )
        )
        public_interest_match = (
            not query_profile.get("is_public_interest")
            or public_interest_boost > 0
            or "公益诉讼" in keywords.get("case_domain", "")
            or record.category == "公益诉讼"
        )
        repeat_point_match = (
            not query_profile.get("is_repeat_point")
            or record.duplicate_count > 1
            or cluster_member_count > 1
        )

        if search_mode == "semantic":
            keep = total_score >= 0.38
        elif search_mode == "keyword":
            keep = bool(keyword_hits)
        else:
            keep = total_score >= 0.24 or bool(keyword_hits) or any((supervision_boost, public_interest_boost, repeat_point_boost))
        keep = keep and supervision_match and public_interest_match and repeat_point_match
        if not keep:
            total_score = 0.0

        explanation = {
            "query": query,
            "search_mode": search_mode,
            "total_score": round(total_score, 4),
            "keyword_score": round(keyword_score, 4),
            "semantic_score": round(semantic_score, 4),
            "supervision_boost": round(supervision_boost, 4),
            "public_interest_boost": round(public_interest_boost, 4),
            "repeat_point_boost": round(repeat_point_boost, 4),
            "keyword_hits": keyword_hits[:6],
            "reasons": self._build_reason_lines(record, keyword_hits, semantic_score),
        }
        return {"record": record, "total_score": total_score, "explanation": explanation}

    def _build_reason_lines(self, record: HotlineRecord, keyword_hits: list[str], semantic_score: float) -> list[str]:
        reason_lines: list[str] = []
        keywords = record.semantic_keywords_json or {}
        if keyword_hits:
            direct_hits = "、".join(keyword_hits[:4])
            reason_lines.append(f"命中关键词/扩展词：{direct_hits}")
        if keywords.get("governance_terms"):
            reason_lines.append(f"命中履职治理表达：{'、'.join(keywords['governance_terms'][:2])}")
        if keywords.get("case_domain"):
            reason_lines.append(f"成案领域：{keywords['case_domain']}")
        if keywords.get("repeat_terms"):
            reason_lines.append(f"存在重复投诉线索：{'、'.join(keywords['repeat_terms'][:2])}")
        if keywords.get("legal_domain"):
            reason_lines.append(f"法定领域：{keywords['legal_domain']}")
        if keywords.get("warning_flags"):
            reason_lines.append(f"预警标记：{'、'.join(keywords['warning_flags'][:2])}")
        if semantic_score >= 0.52:
            reason_lines.append(f"与查询语义相近，语义分 {round(semantic_score, 4)}")
        point_label = (record.normalized_point_json or {}).get("point_label") or record.location_text or ""
        if point_label:
            reason_lines.append(f"关联点位：{point_label}")
        if record.category and record.category != "其他":
            reason_lines.append(f"当前筛查类别：{record.category}")
        return reason_lines[:5]

    @staticmethod
    def _score_supervision_intent(query_profile: dict, keywords: dict, text_blob: str) -> float:
        if not query_profile.get("is_supervision"):
            return 0.0
        score = 0.0
        if keywords.get("governance_terms"):
            score += min(0.18, len(keywords["governance_terms"]) * 0.05)
        case_domain = keywords.get("case_domain", "")
        if "公益诉讼" in case_domain or "行政检察" in case_domain:
            score += 0.12
        if any(token in text_blob for token in ("行业主管部门", "依法处理", "核实责任主体", "督促整改")):
            score += 0.08
        return round(score, 4)

    @staticmethod
    def _score_public_interest_intent(query_profile: dict, keywords: dict, record: HotlineRecord) -> float:
        if not query_profile.get("is_public_interest"):
            return 0.0
        score = 0.0
        case_domain = keywords.get("case_domain", "")
        if "公益诉讼" in case_domain:
            score += 0.2
        if record.category == "公益诉讼":
            score += 0.08
        if record.public_interest_level == "公益":
            score += 0.16
        if record.legal_domain:
            score += 0.06
        if keywords.get("place_type") in {"市场", "河道", "公园", "道路", "学校"}:
            score += 0.04
        return round(score, 4)

    @staticmethod
    def _score_repeat_point_intent(query_profile: dict, record: HotlineRecord, text_blob: str) -> float:
        if not query_profile.get("is_repeat_point"):
            return 0.0
        score = 0.0
        if record.duplicate_count and record.duplicate_count > 1:
            score += min(0.18, record.duplicate_count * 0.04)
        cluster_member_count = SemanticSearchService._cluster_member_count(record)
        if cluster_member_count > 1:
            score += min(0.22, cluster_member_count * 0.03)
        if record.category in {"公益诉讼", "行政违法监督"}:
            score += 0.08
        if any(token in text_blob for token in ("多次投诉", "重复投诉", "投诉集中", "已多次与现场人员沟通未果")):
            score += 0.08
        if record.warning_level in {"中", "高"}:
            score += 0.06
        return round(score, 4)

    @staticmethod
    def _cluster_member_count(record: HotlineRecord) -> int:
        cluster_member_count = len((record.aggressive_cluster_json or {}).get("member_ids", []))
        if record.point_cluster_id:
            cluster_member_count = max(cluster_member_count, 2)
        return cluster_member_count

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = sqrt(sum(value * value for value in left))
        right_norm = sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return round(dot / (left_norm * right_norm), 4)
