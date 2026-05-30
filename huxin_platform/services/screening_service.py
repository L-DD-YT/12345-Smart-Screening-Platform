from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from huxin_platform.services.dedup_service import DedupService
from huxin_platform.services.feature_service import FeatureService
from huxin_platform.services.inference_service import InferenceService
from huxin_platform.services.location_service import LocationService
from huxin_platform.services.point_aggregation_service import PointAggregationService


@dataclass(frozen=True)
class RuleDefinition:
    category: str
    subcategory: str
    keywords: tuple[str, ...]


class ScreeningService:
    """Hybrid screening engine with rules, local ML, and semantic reranking."""

    RULES: tuple[RuleDefinition, ...] = (
        RuleDefinition("民事支持起诉", "欠薪维权", ("拖欠工资", "欠薪", "讨薪", "工资未发", "不发工资", "农民工工资")),
        RuleDefinition("民事支持起诉", "弱势群体保护", ("家暴", "家庭暴力", "虐待", "残疾人", "未成年人", "老人被欺负")),
        RuleDefinition("行政违法监督", "处罚过重", ("处罚太重", "过重处罚", "小过重罚", "罚款过高", "同案不同罚")),
        RuleDefinition("行政违法监督", "执法不规范", ("执法不规范", "乱罚款", "执法随意", "程序违法", "重复处罚")),
        RuleDefinition("公益诉讼", "公共环境治理", ("污水", "垃圾堆放", "油烟扰民", "河道污染", "非法倾倒", "黑臭水体")),
        RuleDefinition("公益诉讼", "公共安全治理", ("消防通道", "占道经营", "井盖破损", "无证排污", "噪声污染")),
        RuleDefinition("刑事犯罪线索", "人身侵害", ("故意伤害", "家暴致伤", "虐待儿童", "非法拘禁")),
        RuleDefinition("刑事犯罪线索", "财产侵害", ("诈骗", "非法集资", "传销", "强迫交易")),
    )

    def __init__(self) -> None:
        self.feature_service = FeatureService()
        self.location_service = LocationService()
        self.dedup_service = DedupService()
        self.inference_service = InferenceService()
        self.point_aggregation_service = PointAggregationService()

    def build_duplicate_key(
        self,
        complaint_text: str,
        location_text: str | None,
        district: str | None,
        complainant_name: str | None = None,
        complainant_phone: str | None = None,
    ) -> str:
        return self.dedup_service.build_duplicate_key(
            complaint_text,
            location_text,
            district,
            complainant_name=complainant_name,
            complainant_phone=complainant_phone,
        )

    def build_duplicate_signals(
        self,
        complaint_text: str,
        location_text: str | None,
        district: str | None,
        complainant_name: str | None = None,
        complainant_phone: str | None = None,
    ) -> dict:
        return self.dedup_service.build_duplicate_signals(
            complaint_text,
            location_text,
            district,
            complainant_name=complainant_name,
            complainant_phone=complainant_phone,
        )

    def classify_duplicate_level(
        self,
        *,
        duplicate_count: int,
        weak_match_count: int = 0,
        person_match_count: int = 0,
    ) -> tuple[str, list[str]]:
        return self.dedup_service.classify_duplicate_level(
            duplicate_count=duplicate_count,
            weak_match_count=weak_match_count,
            person_match_count=person_match_count,
        )

    def get_runtime_versions(self) -> dict[str, str]:
        return self.inference_service.get_runtime_versions()

    def analyze_record(
        self,
        complaint_text: str,
        location_text: str | None,
        district: str | None,
        duplicate_count: int,
        duplicate_group: str,
        resolved_status: str = "待核实",
        satisfaction_status: str = "待核实",
        response_status: str = "待核实",
        first_seen_at: datetime | None = None,
        last_seen_at: datetime | None = None,
        complainant_name: str | None = None,
        complainant_phone: str | None = None,
        weak_match_count: int = 0,
        person_match_count: int = 0,
    ) -> dict:
        matched_rules = self._match_rules(complaint_text)
        matched_rules.extend(self._match_metadata_rules(complaint_text))
        rule_category, rule_subcategory = self._pick_category(matched_rules)
        has_location, normalized_location = self.location_service.detect_location(complaint_text, location_text, district)
        structured_fields = self._extract_structured_fields(complaint_text, normalized_location)
        point_profile = self.point_aggregation_service.build_record_point_profile(
            complaint_text,
            normalized_location,
            district,
        )
        model_prediction = self.inference_service.predict(
            complaint_text,
            matched_rules=matched_rules,
            district=district,
            location_text=normalized_location,
        )
        predicted_category = model_prediction["category"] or ""
        if rule_category != "其他" and predicted_category in {"", "其他"}:
            category = rule_category
        else:
            category = predicted_category or rule_category
        subcategory = (
            rule_subcategory
            if category == rule_category and rule_subcategory != "待人工识别"
            else model_prediction["subcategory"]
        )
        public_interest = self.feature_service.evaluate_public_interest(
            complaint_text=complaint_text,
            category=category,
            has_location=has_location,
            duplicate_count=duplicate_count,
            domain_matches=[],
            domain_decision=None,
        )
        domain_decision = self.feature_service.empty_legal_domain_decision()
        if public_interest["level"] in {"公益", "待复核"}:
            domain_decision = self.feature_service.resolve_legal_domain_decision(
                complaint_text,
                fallback_to_other=public_interest["level"] == "公益",
            )
        legal_domain = domain_decision["primary_domain"]
        domain_matches = [
            {"domain": item["name"], "score": item["score"], "matched_terms": item["matched_terms"]}
            for item in domain_decision["candidates"]
            if item.get("name")
        ]
        duplicate_level, duplicate_reasons = self.classify_duplicate_level(
            duplicate_count=duplicate_count,
            weak_match_count=weak_match_count,
            person_match_count=person_match_count,
        )
        is_duplicate = duplicate_count > 1 or duplicate_level in {"强重复", "弱重复"}
        is_procuratorial = category != "其他"

        if category == "公益诉讼" and (not has_location or public_interest["level"] == "私益"):
            is_procuratorial = False

        duration_days = self._compute_duration_days(first_seen_at, last_seen_at)

        assessment_confidence = self._compute_assessment_confidence(
            category=category,
            model_confidence=model_prediction["confidence"],
            matched_rules=matched_rules,
            has_location=has_location,
            duplicate_count=duplicate_count,
            complaint_text=complaint_text,
            ensemble_prediction=model_prediction["ensemble_prediction_json"],
        )
        risk_level = self._compute_risk_level(
            category=category,
            duplicate_count=duplicate_count,
            has_location=has_location,
            structured_fields=structured_fields,
            complaint_text=complaint_text,
            is_procuratorial=is_procuratorial,
            confidence=assessment_confidence,
            matched_rules=matched_rules,
            public_interest_level=public_interest["level"],
            duration_days=duration_days,
            resolved_status=resolved_status,
        )
        priority_level, priority_reason = self._compute_priority_level(
            category=category,
            public_interest_level=public_interest["level"],
            duplicate_count=duplicate_count,
            duration_days=duration_days,
            warning_level="无",
            has_location=has_location,
            risk_level=risk_level,
        )
        warning_level, warning_flags, warning_summary = self._compute_warning_level(
            duplicate_count=duplicate_count,
            duration_days=duration_days,
            resolved_status=resolved_status,
            satisfaction_status=satisfaction_status,
            risk_level=risk_level,
            duplicate_level=duplicate_level,
            person_match_count=person_match_count,
        )
        priority_level, priority_reason = self._compute_priority_level(
            category=category,
            public_interest_level=public_interest["level"],
            duplicate_count=duplicate_count,
            duration_days=duration_days,
            warning_level=warning_level,
            has_location=has_location,
            risk_level=risk_level,
        )

        screening_summary = self._build_summary(
            category=category,
            subcategory=subcategory,
            risk_level=risk_level,
            priority_level=priority_level,
            confidence=assessment_confidence,
            is_duplicate=is_duplicate,
            duplicate_count=duplicate_count,
            has_location=has_location,
            is_procuratorial=is_procuratorial,
            structured_fields=structured_fields,
            public_interest_level=public_interest["level"],
            legal_domain=legal_domain,
            warning_level=warning_level,
        )
        semantic_keywords = self._build_semantic_keywords(
            complaint_text=complaint_text,
            matched_rules=matched_rules,
            point_profile=point_profile,
            category=category,
            legal_domain=legal_domain,
            public_interest_level=public_interest["level"],
            warning_flags=warning_flags,
        )

        return {
            "status": "已筛查",
            "has_location": has_location,
            "is_duplicate": is_duplicate,
            "duplicate_group": duplicate_group,
            "duplicate_count": duplicate_count,
            "duplicate_level": duplicate_level,
            "duplicate_reasons_json": duplicate_reasons,
            "category": category,
            "subcategory": subcategory,
            "procuratorial_type": category if is_procuratorial else "其他",
            "is_procuratorial": is_procuratorial,
            "risk_level": risk_level,
            "priority_level": priority_level,
            "priority_reason": priority_reason,
            "public_interest_level": public_interest["level"],
            "public_interest_score": public_interest["score"],
            "public_interest_reasons_json": public_interest["reasons"],
            "public_interest_evidence_json": public_interest.get("evidence", {}),
            "legal_domain": legal_domain or None,
            "domain_confidence": domain_decision["confidence"],
            "domain_tags_json": [item["domain"] for item in domain_matches],
            "domain_candidates_json": domain_decision["candidates"],
            "domain_conflict_flags_json": domain_decision["conflict_flags"],
            "resolved_status": resolved_status,
            "satisfaction_status": satisfaction_status,
            "response_status": response_status,
            "warning_level": warning_level,
            "warning_flags_json": warning_flags,
            "warning_reason_summary": warning_summary,
            "performance_anomaly_level": "无",
            "performance_anomaly_reasons_json": [],
            "duration_days": duration_days,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "screening_version": self.get_runtime_versions()["screening_version"],
            "model_version": model_prediction["model_version"],
            "feature_version": model_prediction["feature_version"],
            "screening_confidence": assessment_confidence,
            "matched_rules_json": matched_rules,
            "structured_fields_json": structured_fields,
            "ml_prediction_json": model_prediction["ml_prediction_json"],
            "dl_prediction_json": model_prediction["dl_prediction_json"],
            "ensemble_prediction_json": model_prediction["ensemble_prediction_json"],
            "semantic_keywords_json": semantic_keywords,
            "normalized_point_json": point_profile,
            "semantic_vector_json": [],
            "point_cluster_id": None,
            "point_cluster_label": None,
            "aggressive_cluster_json": {},
            "screening_summary": screening_summary,
        }

    def explain_record(self, record: object) -> dict:
        matched_rules = getattr(record, "matched_rules_json", []) or []
        structured_fields = getattr(record, "structured_fields_json", {}) or {}
        ensemble_prediction = getattr(record, "ensemble_prediction_json", {}) or {}
        warning_flags = getattr(record, "warning_flags_json", []) or []
        public_interest_reasons = getattr(record, "public_interest_reasons_json", []) or []
        location = getattr(record, "location_text", "") or structured_fields.get("point_location") or "未识别"
        key_points = [
            f"系统判定类别：{getattr(record, 'category', '待识别')} / {getattr(record, 'subcategory', '待识别') or '待识别'}。",
            f"风险等级：{getattr(record, 'risk_level', '低')}，优先级：{getattr(record, 'priority_level', '低')}，人工办理状态：{getattr(record, 'handling_status', '待研判')}。",
            f"公益属性：{getattr(record, 'public_interest_level', '待复核')}，法定领域：{self._display_legal_domain(getattr(record, 'public_interest_level', '待复核'), getattr(record, 'legal_domain', '') or '')}。",
            f"点位信息：{location}，是否重复投诉：{'是' if getattr(record, 'is_duplicate', False) else '否'}。",
            f"综合置信度：{round(float(getattr(record, 'screening_confidence', 0.0) or 0.0) * 100, 1)}%，模型版本：{getattr(record, 'model_version', 'rules-v2') or 'rules-v2'}。",
        ]
        if getattr(record, "duration_days", 0):
            key_points.append(f"同事项持续时长：约 {getattr(record, 'duration_days', 0)} 天。")
        if warning_flags:
            key_points.append(f"预警标记：{'；'.join(warning_flags[:4])}。")
        if public_interest_reasons:
            key_points.append(f"公益判定依据：{'；'.join(public_interest_reasons[:3])}。")
        if structured_fields.get("wage_amount"):
            key_points.append(f"抽取到欠薪金额：{structured_fields['wage_amount']}。")
        if structured_fields.get("project_name"):
            key_points.append(f"抽取到项目名称：{structured_fields['project_name']}。")
        if structured_fields.get("worker_count"):
            key_points.append(f"抽取到涉事人数：{structured_fields['worker_count']}。")
        if ensemble_prediction.get("top_candidates"):
            top_candidates = "；".join(
                f"{item['label']} {round(float(item['score']) * 100, 1)}%"
                for item in ensemble_prediction["top_candidates"]
            )
            key_points.append(f"综合模型排序：{top_candidates}。")

        rule_lines = []
        for item in matched_rules:
            keyword = item.get("keyword", "关键词")
            reason = item.get("reason", "命中规则")
            rule_lines.append(f"{keyword}：{reason}")

        if not rule_lines:
            rule_lines.append("未命中强规则，当前以弱匹配与人工复核为主。")

        recommendation = "建议优先进入人工复核。"
        if getattr(record, "category", "") == "公益诉讼" and not getattr(record, "has_location", False):
            recommendation = "建议补充具体点位后再作为公益诉讼候选线索处理。"
        elif getattr(record, "risk_level", "") == "高":
            recommendation = "建议优先纳入高风险涉检线索台账，尽快进行复核。"
        elif getattr(record, "warning_level", "") in {"中", "高"}:
            recommendation = "建议按预警工单处理，优先核查是否存在久拖未决或群众持续不满意情形。"

        return {
            "summary": getattr(record, "screening_summary", "") or "暂无说明。",
            "key_points": key_points,
            "matched_rules": rule_lines,
            "recommendation": recommendation,
        }

    def _match_rules(self, complaint_text: str) -> list[dict]:
        matched: list[dict] = []
        for rule in self.RULES:
            for keyword in rule.keywords:
                if keyword in complaint_text:
                    matched.append(
                        {
                            "category": rule.category,
                            "subcategory": rule.subcategory,
                            "keyword": keyword,
                            "reason": f"命中“{rule.subcategory}”规则关键词",
                        }
                    )
        return matched

    def _match_metadata_rules(self, complaint_text: str) -> list[dict]:
        matched: list[dict] = []
        case_domain = self._match_first(
            complaint_text,
            [r"成案领域[：: ]?([^\n]+)"],
        )
        issue_category = self._match_first(
            complaint_text,
            [r"问题分类[：: ]?([^\n]+)"],
        )
        hinted_category = self.feature_service.infer_category_from_external_hints(
            case_domain,
            issue_category,
            complaint_text,
        )
        if hinted_category:
            matched.append(
                {
                    "category": hinted_category,
                    "subcategory": "领域映射",
                    "keyword": case_domain or issue_category or hinted_category,
                    "reason": "命中成案领域/问题分类映射规则",
                }
            )
        return matched

    def _pick_category(self, matched_rules: list[dict]) -> tuple[str, str]:
        if not matched_rules:
            return "其他", "待人工识别"

        score_board: dict[tuple[str, str], int] = {}
        for item in matched_rules:
            key = (item["category"], item["subcategory"])
            score_board[key] = score_board.get(key, 0) + 1

        category, subcategory = max(score_board.items(), key=lambda item: item[1])[0]
        return category, subcategory

    def _extract_structured_fields(self, complaint_text: str, normalized_location: str) -> dict:
        amount = self._extract_money(complaint_text)
        project_name = self._match_first(
            complaint_text,
            [
                r"([一-龥A-Za-z0-9]{2,24}(?:项目|工地|工程|小区))",
                r"(?:项目名称|工程名称)[：: ]?([^\s，。；]{2,24})",
            ],
        )
        start_time = self._match_first(
            complaint_text,
            [
                r"((?:20\d{2}|19\d{2})年\d{1,2}月(?:\d{1,2}日)?)",
                r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            ],
        )
        worker_count = self._match_first(
            complaint_text,
            [
                r"(\d+)\s*(?:名|位)?(?:工人|工友|员工|农民工)",
                r"(?:共|约)(\d+)(?:人|名)",
            ],
        )
        employer = self._match_first(
            complaint_text,
            [
                r"([一-龥A-Za-z0-9]{2,30}(?:公司|集团|项目部|物业|中心|厂))",
            ],
        )

        contract_signed = "待核实"
        if re.search(r"(未签|没签|未订立).{0,6}劳动合同", complaint_text):
            contract_signed = "否"
        elif "签订劳动合同" in complaint_text or "已签劳动合同" in complaint_text:
            contract_signed = "是"

        return {
            "project_name": project_name or "",
            "point_location": normalized_location or "",
            "start_time": start_time or "",
            "worker_count": f"{worker_count}人" if worker_count else "",
            "arrears_subject": employer or "",
            "wage_amount": amount or "",
            "labor_contract_signed": contract_signed,
        }

    def _build_semantic_keywords(
        self,
        *,
        complaint_text: str,
        matched_rules: list[dict],
        point_profile: dict,
        category: str,
        legal_domain: str,
        public_interest_level: str,
        warning_flags: list[str],
    ) -> dict:
        matched_terms = [item.get("keyword", "") for item in matched_rules if item.get("keyword")]
        return {
            "matched_terms": sorted(set(matched_terms))[:20],
            "category_terms": [category] if category else [],
            "aliases": point_profile.get("alias_candidates", []),
            "place_type": point_profile.get("place_type", ""),
            "point_label": point_profile.get("point_label", ""),
            "legal_domain": legal_domain,
            "public_interest_level": public_interest_level,
            "warning_flags": warning_flags[:6],
            "complaint_preview": complaint_text[:80],
        }

    def _compute_risk_level(
        self,
        category: str,
        duplicate_count: int,
        has_location: bool,
        structured_fields: dict,
        complaint_text: str,
        is_procuratorial: bool,
        confidence: float,
        matched_rules: list[dict],
        public_interest_level: str,
        duration_days: int,
        resolved_status: str,
    ) -> str:
        wage_amount_value = self._parse_amount(structured_fields.get("wage_amount", ""))
        strong_metadata_hit = any(item.get("subcategory") == "领域映射" for item in matched_rules)
        if category == "刑事犯罪线索":
            return "高"
        if public_interest_level == "公益" and duplicate_count >= 3 and duration_days >= 30:
            return "高"
        if category == "公益诉讼" and has_location and duplicate_count >= 2:
            return "高"
        if category == "行政违法监督" and any(token in complaint_text for token in ("小过重罚", "同案不同罚", "重复处罚")):
            return "高"
        if category == "民事支持起诉" and wage_amount_value >= 50000:
            return "高"
        if resolved_status == "未解决" and duplicate_count >= 3:
            return "高"
        if confidence >= 0.94 and category != "其他" and duplicate_count >= 2 and (
            strong_metadata_hit or len(matched_rules) >= 3
        ):
            return "高"
        medium_score = 0
        if is_procuratorial:
            medium_score += 1
        if duplicate_count >= 2:
            medium_score += 1
        if has_location and category == "公益诉讼":
            medium_score += 1
        if confidence >= 0.45 and category != "其他":
            medium_score += 1
        if strong_metadata_hit and category != "其他":
            medium_score += 1
        if public_interest_level == "公益":
            medium_score += 1
        if duration_days >= 30:
            medium_score += 1
        if medium_score >= 2:
            return "中"
        return "低"

    def _compute_assessment_confidence(
        self,
        *,
        category: str,
        model_confidence: float,
        matched_rules: list[dict],
        has_location: bool,
        duplicate_count: int,
        complaint_text: str,
        ensemble_prediction: dict,
    ) -> float:
        base_confidence = float(model_confidence or 0.0)
        rule_strength = min(1.0, len(matched_rules) / 4)
        metadata_hit = any(item.get("subcategory") == "领域映射" for item in matched_rules)
        governance_hit = any(
            token in complaint_text for token in ("核查", "整改", "依法处理", "联合执法", "回头看")
        ) and category != "其他"
        location_strength = 1.0 if (has_location and category == "公益诉讼") else 0.0
        duplicate_strength = min(1.0, duplicate_count / 3) if category != "其他" else 0.0
        confidence = (
            base_confidence * 0.72
            + rule_strength * 0.10
            + (0.07 if metadata_hit else 0.0)
            + location_strength * 0.04
            + duplicate_strength * 0.03
            + (0.04 if governance_hit else 0.0)
        )
        top_candidates = ensemble_prediction.get("top_candidates", []) if isinstance(ensemble_prediction, dict) else []
        if len(top_candidates) >= 2:
            gap = float(top_candidates[0].get("score", 0.0)) - float(top_candidates[1].get("score", 0.0))
            if gap >= 0.12:
                confidence += 0.04
            elif gap >= 0.06:
                confidence += 0.02
        if category != "其他" and len(matched_rules) >= 2:
            confidence = max(confidence, 0.42)
        if category == "其他":
            confidence = min(confidence, 0.42)
        return round(min(confidence, 0.88), 4)

    def _build_summary(
        self,
        category: str,
        subcategory: str,
        risk_level: str,
        priority_level: str,
        confidence: float,
        is_duplicate: bool,
        duplicate_count: int,
        has_location: bool,
        is_procuratorial: bool,
        structured_fields: dict,
        public_interest_level: str,
        legal_domain: str,
        warning_level: str,
    ) -> str:
        summary_parts = [f"系统识别为“{category}”"]
        if subcategory and subcategory != "待人工识别":
            summary_parts.append(f"细分场景为“{subcategory}”")
        summary_parts.append(f"风险等级为“{risk_level}”")
        summary_parts.append(f"办理优先级为“{priority_level}”")
        summary_parts.append(f"公益属性判定为“{public_interest_level}”")
        if public_interest_level == "公益" and legal_domain:
            summary_parts.append(f"法定领域为“{legal_domain}”")
        elif public_interest_level == "公益":
            summary_parts.append("法定领域待细化")
        summary_parts.append(f"综合置信度 {round(confidence * 100, 1)}%")
        summary_parts.append("具备涉检线索价值" if is_procuratorial else "暂不直接纳入涉检线索")
        if is_duplicate:
            summary_parts.append(f"发现重复投诉 {duplicate_count} 条")
        if has_location:
            summary_parts.append("已识别具体点位")
        else:
            summary_parts.append("未识别到明确点位")
        if warning_level != "无":
            summary_parts.append(f"触发“{warning_level}”级预警")
        if structured_fields.get("wage_amount"):
            summary_parts.append(f"抽取到欠薪金额 {structured_fields['wage_amount']}")
        return "，".join(summary_parts) + "。"

    @staticmethod
    def _compute_duration_days(first_seen_at: datetime | None, last_seen_at: datetime | None) -> int:
        if not first_seen_at or not last_seen_at:
            return 0
        return max(0, (last_seen_at.date() - first_seen_at.date()).days)

    def _compute_warning_level(
        self,
        *,
        duplicate_count: int,
        duration_days: int,
        resolved_status: str,
        satisfaction_status: str,
        risk_level: str,
        duplicate_level: str = "无",
        person_match_count: int = 0,
    ) -> tuple[str, list[str], str]:
        flags: list[str] = []
        if duplicate_count >= 10:
            flags.append("重复投诉达到10次以上")
        elif duplicate_count >= 5:
            flags.append("重复投诉达到5次以上")
        elif duplicate_count >= 3:
            flags.append("重复投诉达到3次以上")
        if person_match_count >= 3:
            flags.append("同一投诉人多次反映同事项")
        if duplicate_level == "同区域同类高频":
            flags.append("同区域同类问题集中爆发")
        if duration_days >= 30:
            flags.append("持续30天以上未见明显化解")
        if resolved_status == "未解决":
            flags.append("工单状态显示未解决")
        if satisfaction_status == "不满意":
            flags.append("群众反馈不满意")
        if duration_days >= 30 and satisfaction_status == "不满意":
            flags.append("整改未达预期，群众持续不满意")
        if duplicate_count >= 3 and satisfaction_status == "不满意":
            flags.append("多次办理仍不满意")
        if risk_level == "高":
            flags.append("当前已判定为高风险线索")

        level = "无"
        if (
            duplicate_count >= 10
            or (duration_days >= 30 and satisfaction_status == "不满意")
            or len(flags) >= 4
            or duplicate_level == "强重复" and satisfaction_status == "不满意"
        ):
            level = "高"
        elif (
            duplicate_count >= 5
            or duration_days >= 30
            or satisfaction_status == "不满意"
            or duplicate_level == "同区域同类高频"
        ):
            level = "中"
        elif flags:
            level = "低"

        summary = self._build_warning_summary(level=level, flags=flags)
        return level, flags[:6], summary

    @staticmethod
    def _build_warning_summary(*, level: str, flags: list[str]) -> str:
        if level == "无":
            return "暂未触发预警条件"
        head = {
            "高": "高等级预警",
            "中": "中等级预警",
            "低": "低等级预警",
        }.get(level, "预警")
        if not flags:
            return f"{head}：综合多项指标判断"
        return f"{head}：{'；'.join(flags[:3])}"

    @staticmethod
    def _compute_priority_level(
        *,
        category: str,
        public_interest_level: str,
        duplicate_count: int,
        duration_days: int,
        warning_level: str,
        has_location: bool,
        risk_level: str,
    ) -> tuple[str, str]:
        if risk_level == "高" or warning_level == "高":
            return "高", "风险或预警等级较高，建议优先研判。"
        if category == "公益诉讼" and public_interest_level == "公益" and has_location and duplicate_count >= 2:
            return "高", "公益属性明确，且具备点位与重复投诉支撑。"
        if warning_level == "中" or duration_days >= 30:
            return "中", "存在持续反映或中等级预警，建议尽快复核。"
        if public_interest_level == "公益":
            return "中", "具备公共利益受损特征，建议纳入重点关注。"
        return "低", "暂未达到优先办理阈值，可继续观察或人工补充信息。"

    @staticmethod
    def _match_first(text: str, patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _display_legal_domain(public_interest_level: str, legal_domain: str) -> str:
        if public_interest_level == "私益":
            return "不适用"
        if public_interest_level == "公益" and not legal_domain:
            return "待细化"
        if public_interest_level == "待复核" and not legal_domain:
            return "待复核"
        return legal_domain or "待补充"

    @staticmethod
    def _extract_money(text: str) -> str:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(万元|元)", text)
        if not match:
            return ""
        amount = float(match.group(1))
        unit = match.group(2)
        if unit == "万元":
            amount *= 10000
        if amount.is_integer():
            return f"{int(amount)}元"
        return f"{round(amount, 2)}元"

    @staticmethod
    def _parse_amount(value: str) -> float:
        if not value:
            return 0.0
        normalized = value.replace("元", "").replace(",", "").strip()
        try:
            return float(normalized)
        except ValueError:
            return 0.0
