from __future__ import annotations

import csv
import math
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from huxin_platform.core.config import settings
from huxin_platform.models.entities import (
    ExportRecord,
    ExternalSyncRecord,
    HotlineRecord,
    LLMCallLog,
    ModelArtifactRecord,
    PushTaskRecord,
    ScreeningJobRecord,
)
from huxin_platform.services.feature_service import FeatureService


FANGSHAN_AREAS: tuple[str, ...] = (
    "城关街道",
    "新镇街道",
    "向阳街道",
    "东风街道",
    "迎风街道",
    "西潞街道",
    "拱辰街道",
    "良乡镇",
    "长阳镇",
    "阎村镇",
    "窦店镇",
    "琉璃河镇",
    "青龙湖镇",
    "周口店镇",
    "张坊镇",
    "十渡镇",
    "韩村河镇",
    "佛子庄乡",
    "霞云岭乡",
    "南窖乡",
    "大石窝镇",
    "石楼镇",
    "蒲洼乡",
    "史家营乡",
    "大安山乡",
    "长沟镇",
    "河北镇",
)


def _format_datetime(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d %H:%M")


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    candidates = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y年%m月%d日",
        "%Y年%m月%d日 %H:%M",
    )
    for pattern in candidates:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _normalize_resolved_status(value: str) -> str:
    text = _clean_cell(value)
    if not text:
        return "待核实"
    if any(token in text for token in ("未解决", "未办结", "未处理", "处理中", "未完成")):
        return "未解决"
    if any(token in text for token in ("已解决", "已办结", "已处理", "办结", "完成")):
        return "已解决"
    return "待核实"


def _normalize_satisfaction_status(value: str) -> str:
    text = _clean_cell(value)
    if not text:
        return "待核实"
    if any(token in text for token in ("不满意", "差评", "未满意", "非常不满意")):
        return "不满意"
    if any(token in text for token in ("满意", "较满意", "非常满意")):
        return "满意"
    return "待核实"


def _normalize_response_status(value: str) -> str:
    text = _clean_cell(value)
    if not text:
        return "待核实"
    if any(token in text for token in ("超时", "逾期", "未响应", "未回复")):
        return "超时"
    if any(token in text for token in ("已响应", "已回复", "已受理", "已联系")):
        return "已响应"
    return "待核实"


def _derive_status_fields(
    *,
    resolved_text: str = "",
    satisfaction_text: str = "",
    handling_result: str = "",
    reply_content: str = "",
    complaint_text: str = "",
) -> dict[str, str]:
    combined = " ".join(part for part in (handling_result, reply_content, complaint_text) if part)
    resolved_status = _normalize_resolved_status(resolved_text or combined)
    satisfaction_status = _normalize_satisfaction_status(satisfaction_text or combined)
    response_status = _normalize_response_status(combined)
    return {
        "resolved_status": resolved_status,
        "satisfaction_status": satisfaction_status,
        "response_status": response_status,
    }


def _apply_record_filters(
    query,
    *,
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
    record_ids: list[int] | None = None,
    only_pending: bool | None = None,
):
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
    if record_ids:
        query = query.where(HotlineRecord.id.in_(record_ids))
    if only_pending is True:
        query = query.where(HotlineRecord.status != "已筛查")
    return query


def _count_query(db: Session, query) -> int:
    return db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _public_domain_label(public_interest_level: str | None, legal_domain: str | None) -> str:
    if public_interest_level == "私益":
        return "不适用"
    if public_interest_level == "公益":
        return legal_domain or "其他"
    return legal_domain or "待复核"


def _domain_bucket_label(public_interest_level: str | None, legal_domain: str | None) -> str:
    if public_interest_level == "公益":
        return legal_domain or "其他"
    return "非公益"


def _pick_first_nonempty(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _clean_cell(row.get(key))
        if value:
            return value
    return ""


def _normalize_import_type(value: str) -> str:
    text = _clean_cell(value)
    if not text:
        return "普通"
    if any(token in text for token in ("举报", "检举")):
        return "举报"
    if "建议" in text:
        return "建议"
    if any(token in text for token in ("求助", "救助", "帮扶")):
        return "求助"
    if any(token in text for token in ("咨询", "询问")):
        return "咨询"
    if any(token in text for token in ("诉求", "投诉")):
        return "诉求"
    if any(token in text for token in ("热线", "工单")):
        return "热线"
    return text[:20]


def _build_import_channel(row: dict[str, Any]) -> str:
    import_type = _normalize_import_type(
        _pick_first_nonempty(row, ("工单类型", "单据类型", "类型", "诉求类型"))
    )
    return f"文件批量导入-{import_type}"


def _build_excel_location_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "被反映区",
        "所属区县",
        "被反映街乡镇",
        "街道",
        "乡镇",
        "村/社区",
        "社区",
        "小区点位",
        "地点",
        "地址",
        "企业名称",
        "公司名称",
    ):
        value = _clean_cell(row.get(key))
        if value and value not in parts:
            parts.append(value)
    return "".join(parts)[:255]


def _build_excel_complaint_text(row: dict[str, Any]) -> str:
    text_parts: list[str] = []
    title = _pick_first_nonempty(row, ("标题", "主题", "事项标题", "问题标题"))
    issue_type = _pick_first_nonempty(row, ("工单类型", "单据类型", "类型", "诉求类型"))
    issue_category = _pick_first_nonempty(row, ("问题分类", "业务分类", "事项分类", "分类"))
    tags = _pick_first_nonempty(row, ("标签", "关键词", "标签词"))
    main_content = _pick_first_nonempty(row, ("主要内容", "内容", "诉求内容", "问题描述", "描述"))
    enterprise_name = _pick_first_nonempty(row, ("企业名称", "公司名称", "涉事单位", "单位名称"))
    case_domain = _pick_first_nonempty(row, ("成案领域", "领域", "案件领域"))
    handling_result = _pick_first_nonempty(row, ("办理结果", "处理结果", "反馈结果"))
    reply_content = _pick_first_nonempty(row, ("回复内容", "答复内容", "处置情况"))
    issue_nature = _pick_first_nonempty(row, ("工单性质", "问题性质", "事项性质"))
    resolved_text = _pick_first_nonempty(row, ("是否解决", "是否已解决"))
    satisfaction_text = _pick_first_nonempty(row, ("是否满意", "满意度"))

    if title:
        text_parts.append(f"标题：{title}")
    if issue_type:
        text_parts.append(f"工单类型：{issue_type}")
    if issue_category:
        text_parts.append(f"问题分类：{issue_category}")
    if issue_nature:
        text_parts.append(f"工单性质：{issue_nature}")
    if tags:
        text_parts.append(f"标签：{tags}")
    if enterprise_name:
        text_parts.append(f"企业名称：{enterprise_name}")
    if case_domain:
        text_parts.append(f"成案领域：{case_domain}")
    if resolved_text:
        text_parts.append(f"是否解决：{resolved_text}")
    if satisfaction_text:
        text_parts.append(f"是否满意：{satisfaction_text}")
    if main_content:
        text_parts.append(f"主要内容：{main_content}")
    if handling_result:
        text_parts.append(f"办理结果：{handling_result}")
    if reply_content:
        text_parts.append(f"回复内容：{reply_content}")

    complaint_text = "\n".join(text_parts).strip()
    if complaint_text:
        return complaint_text
    return title or issue_category or "表格导入工单"


def _build_record_timeline(event_time: str, fallback_created_at: datetime | None = None) -> tuple[datetime | None, datetime | None]:
    parsed_time = _parse_datetime(event_time)
    if parsed_time:
        return parsed_time, parsed_time
    if fallback_created_at:
        return fallback_created_at, fallback_created_at
    return None, None


def _resolve_fangshan_area(record: HotlineRecord) -> str:
    candidates = [
        (record.normalized_point_json or {}).get("street", ""),
        record.location_text or "",
        record.title or "",
        record.complaint_text or "",
    ]
    for candidate in candidates:
        for area in FANGSHAN_AREAS:
            if area and area in candidate:
                return area
    return ""


def _build_fangshan_region_search_keyword(area_name: str) -> str:
    return f"北京市房山区{area_name}"


def _build_fangshan_region_intensity(item: dict[str, Any]) -> int:
    return int(
        (item.get("count", 0) or 0)
        + (item.get("public_interest_count", 0) or 0)
        + (item.get("warning_count", 0) or 0) * 2
        + (item.get("difficult_count", 0) or 0) * 3
    )


def import_spreadsheet_records(db: Session, file_bytes: bytes, filename: str, source: str = "12345") -> dict:
    workbook = pd.ExcelFile(BytesIO(file_bytes))
    existing_records = {
        item.ticket_no: item
        for item in db.scalars(select(HotlineRecord).where(HotlineRecord.ticket_no.is_not(None))).all()
        if item.ticket_no
    }
    created: list[HotlineRecord] = []
    updated: list[HotlineRecord] = []
    skipped_duplicates = 0
    skipped_empty = 0
    parsed_rows = 0
    processed_record_ids: list[int] = []

    for sheet_name in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet_name).fillna("")
        for row in frame.to_dict(orient="records"):
            parsed_rows += 1
            ticket_no = _clean_cell(row.get("工单编号"))
            if not ticket_no:
                skipped_empty += 1
                continue

            title = (
                _pick_first_nonempty(row, ("标题", "主题", "事项标题", "问题标题"))
                or _pick_first_nonempty(row, ("成案领域", "领域", "案件领域"))
                or _pick_first_nonempty(row, ("问题分类", "业务分类", "事项分类", "分类"))
                or ticket_no
            )
            district = _pick_first_nonempty(row, ("被反映区", "所属区县", "区县"))
            event_time = _pick_first_nonempty(row, ("办结时间", "创建时间", "发生时间", "上报时间"))
            location_text = _build_excel_location_text(row)
            handling_result = _pick_first_nonempty(row, ("办理结果", "处理结果", "反馈结果"))
            reply_content = _pick_first_nonempty(row, ("回复内容", "答复内容", "处置情况"))
            resolved_text = _pick_first_nonempty(row, ("是否解决", "是否已解决"))
            satisfaction_text = _pick_first_nonempty(row, ("是否满意", "满意度"))
            status_fields = _derive_status_fields(
                resolved_text=resolved_text,
                satisfaction_text=satisfaction_text,
                handling_result=handling_result,
                reply_content=reply_content,
                complaint_text=_build_excel_complaint_text(row),
            )
            first_seen_at, last_seen_at = _build_record_timeline(event_time)
            payload = {
                "ticket_no": ticket_no,
                "source": source,
                "channel": _build_import_channel(row),
                "title": title[:200],
                "complainant_name": _pick_first_nonempty(row, ("来电人", "姓名", "联系人", "投诉人")) or None,
                "complainant_phone": _pick_first_nonempty(row, ("来电人电话/账号", "联系电话", "电话", "手机号", "账号")) or None,
                "district": district or None,
                "location_text": location_text or None,
                "event_time": event_time or None,
                "complaint_text": _build_excel_complaint_text(row),
                "resolved_status": status_fields["resolved_status"],
                "satisfaction_status": status_fields["satisfaction_status"],
                "response_status": status_fields["response_status"],
                "first_seen_at": first_seen_at,
                "last_seen_at": last_seen_at,
                "raw_payload_json": {
                    "file_name": filename,
                    "sheet_name": sheet_name,
                    **{key: _clean_cell(value) for key, value in row.items()},
                },
            }

            existing_record = existing_records.get(ticket_no)
            if existing_record:
                existing_record.source = payload["source"]
                existing_record.channel = payload["channel"]
                existing_record.title = payload["title"]
                existing_record.complainant_name = payload["complainant_name"]
                existing_record.complainant_phone = payload["complainant_phone"]
                existing_record.district = payload["district"]
                existing_record.location_text = payload["location_text"]
                existing_record.event_time = payload["event_time"]
                existing_record.complaint_text = payload["complaint_text"]
                existing_record.resolved_status = payload["resolved_status"]
                existing_record.satisfaction_status = payload["satisfaction_status"]
                existing_record.response_status = payload["response_status"]
                existing_record.first_seen_at = payload["first_seen_at"]
                existing_record.last_seen_at = payload["last_seen_at"]
                existing_record.raw_payload_json = payload["raw_payload_json"]
                existing_record.status = "待筛查"
                existing_record.screening_summary = None
                existing_record.screened_at = None
                db.add(existing_record)
                updated.append(existing_record)
                processed_record_ids.append(existing_record.id)
                continue

            record = HotlineRecord(**payload)
            db.add(record)
            created.append(record)
            db.flush()
            existing_records[ticket_no] = record
            processed_record_ids.append(record.id)

    db.commit()
    for record in created:
        db.refresh(record)
    for record in updated:
        db.refresh(record)

    return {
        "created_count": len(created),
        "updated_count": len(updated),
        "skipped_duplicates": skipped_duplicates,
        "skipped_empty": skipped_empty,
        "parsed_rows": parsed_rows,
        "sheet_names": workbook.sheet_names,
        "record_ids": processed_record_ids,
        "items": [serialize_record(item) for item in (created + updated)[:5]],
    }


def seed_demo_data(db: Session) -> None:
    """Seed demo rows only for an empty local database."""
    if db.scalar(select(func.count()).select_from(HotlineRecord)) == 0:
        demo_records = [
            {
                "ticket_no": "12345-2026-0001",
                "source": "12345",
                "channel": "市民投诉热线",
                "title": "工地欠薪投诉",
                "complainant_name": "张师傅",
                "complainant_phone": "13800000001",
                "district": "房山区",
                "location_text": "房山区良乡大学城北侧安置房项目",
                "event_time": "2026-04-01 09:30",
                "complaint_text": "反映房山区良乡大学城北侧安置房项目拖欠12名农民工工资共8.6万元，自2025年11月开工至今未足额支付，也没有签劳动合同。",
                "resolved_status": "未解决",
                "satisfaction_status": "不满意",
                "response_status": "已响应",
            },
            {
                "ticket_no": "12345-2026-0002",
                "source": "12345",
                "channel": "市民投诉热线",
                "title": "重复欠薪投诉",
                "complainant_name": "李某",
                "complainant_phone": "13800000002",
                "district": "房山区",
                "location_text": "房山区良乡大学城北侧安置房项目",
                "event_time": "2026-04-02 11:00",
                "complaint_text": "再次投诉房山区良乡大学城北侧安置房项目拖欠工人工资，施工单位北京城建项目部拖欠12名农民工工资8.6万元。",
                "resolved_status": "未解决",
                "satisfaction_status": "不满意",
                "response_status": "已响应",
            },
            {
                "ticket_no": "12345-2026-0003",
                "source": "12345",
                "channel": "市民投诉热线",
                "title": "企业行政处罚争议",
                "complainant_name": "王经理",
                "complainant_phone": "13800000003",
                "district": "房山区",
                "location_text": "房山区阎村镇工业园",
                "event_time": "2026-04-04 15:10",
                "complaint_text": "企业反映阎村镇工业园某执法单位存在小过重罚、同案不同罚问题，同样情形被处以远高于周边企业的罚款，怀疑执法程序不规范。",
            },
            {
                "ticket_no": "12345-2026-0004",
                "source": "街道综治",
                "channel": "街道转办",
                "title": "河道污染反复投诉",
                "complainant_name": "赵女士",
                "complainant_phone": "13800000004",
                "district": "房山区",
                "location_text": "房山区长阳镇清河沿岸",
                "event_time": "2026-04-05 08:40",
                "complaint_text": "多次反映房山区长阳镇清河沿岸存在污水直排和垃圾堆放，附近居民已连续投诉三次，希望尽快整治。",
                "resolved_status": "未解决",
                "satisfaction_status": "不满意",
                "response_status": "已响应",
            },
            {
                "ticket_no": "12345-2026-0005",
                "source": "检察业务",
                "channel": "业务移送",
                "title": "疑似诈骗线索",
                "complainant_name": "刘先生",
                "complainant_phone": "13800000005",
                "district": "房山区",
                "location_text": "房山区拱辰街道某培训机构",
                "event_time": "2026-04-06 14:20",
                "complaint_text": "反映房山区拱辰街道某培训机构以退费名义持续收钱，疑似诈骗，多名家长已被骗。",
            },
            {
                "ticket_no": "12345-2026-0006",
                "source": "12345",
                "channel": "市民投诉热线",
                "title": "无点位公益投诉",
                "complainant_name": "匿名",
                "complainant_phone": "",
                "district": "房山区",
                "location_text": "",
                "event_time": "2026-04-07 10:00",
                "complaint_text": "反映有地方长期堆放垃圾并伴随恶臭，希望有关部门核查。",
            },
        ]
        for payload in demo_records:
            db.add(HotlineRecord(**payload, raw_payload_json=payload))
        db.commit()
        run_screening(db, only_pending=False)

        first_record = db.scalars(select(HotlineRecord).order_by(HotlineRecord.id.asc())).first()
        if first_record:
            first_record.review_status = "已标注"
            first_record.manual_label = "建议移送民事支持起诉"
            first_record.handling_status = "待复核"
            first_record.review_comment = "已具备欠薪金额、人数和项目点位，适合作为支持起诉候选线索。"
            first_record.reviewed_at = datetime.utcnow()
            db.add(first_record)

    if db.scalar(select(func.count()).select_from(ExternalSyncRecord)) == 0:
        db.add_all(
            [
                ExternalSyncRecord(source_system="12345", mode="demo", raw_external_id="12345-DEMO-001", sync_status="可演示拉取", normalized_summary="12345 工单来源已配置"),
                ExternalSyncRecord(source_system="街道综治", mode="demo", raw_external_id="STREET-DEMO-001", sync_status="可演示拉取", normalized_summary="街道综治来源已配置"),
                ExternalSyncRecord(source_system="检察业务", mode="demo", raw_external_id="PROC-DEMO-001", sync_status="可演示拉取", normalized_summary="检察业务来源已配置"),
            ]
        )

    if db.scalar(select(func.count()).select_from(ExportRecord)) == 0:
        db.add(
            ExportRecord(
                export_scope="初始化演示台账",
                export_format="csv",
                item_count=3,
                file_name="hotline_screening_demo.csv",
                remark="系统初始化时生成的演示导出记录。",
            )
        )

    db.commit()


def _effective_record_datetime(record: HotlineRecord) -> datetime:
    return _parse_datetime(record.event_time) or record.created_at


def _build_month_labels(records: list[HotlineRecord], limit: int = 6) -> list[str]:
    labels = sorted({_effective_record_datetime(record).strftime("%Y-%m") for record in records})
    if not labels:
        labels = [datetime.utcnow().strftime("%Y-%m")]
    return labels[-limit:]


def _build_month_series(records: list[HotlineRecord], labels: list[str], predicate=None) -> list[dict]:
    counter = {label: 0 for label in labels}
    for record in records:
        bucket = _effective_record_datetime(record).strftime("%Y-%m")
        if bucket not in counter:
            continue
        if predicate and not predicate(record):
            continue
        counter[bucket] += 1
    return [{"label": label, "count": counter[label]} for label in labels]


def _build_domain_trends(records: list[HotlineRecord], labels: list[str], top_k: int = 4) -> list[dict]:
    legal_domains = FeatureService().list_legal_domains()
    domain_counts = {name: 0 for name in legal_domains}
    for record in records:
        if record.public_interest_level == "公益" and record.legal_domain in domain_counts:
            domain_counts[record.legal_domain] += 1
    top_domains = [name for name in legal_domains if domain_counts.get(name, 0) > 0][: max(top_k, len(legal_domains))]
    trends: list[dict] = []
    for domain in top_domains:
        series = _build_month_series(
            records,
            labels,
            predicate=lambda item, d=domain: item.public_interest_level == "公益" and item.legal_domain == d,
        )
        trends.append({"domain": domain, "series": series})
    return trends


def _summarize_area_trend(series: list[dict]) -> tuple[str, str]:
    if len(series) < 2:
        return "平稳", "近期待势平稳"
    counts = [item.get("count", 0) or 0 for item in series]
    left_size = max(1, len(counts) // 2)
    first_avg = sum(counts[:left_size]) / max(left_size, 1)
    last_avg = sum(counts[-left_size:]) / max(left_size, 1)
    delta = last_avg - first_avg
    if delta >= 1:
        return "升温", f"近期待势上升，月均较前段提升 {round(delta, 1)} 条"
    if delta <= -1:
        return "回落", f"近期待势回落，月均较前段下降 {round(abs(delta), 1)} 条"
    return "平稳", "近期待势平稳，无明显波动"


def build_analysis_payload(db: Session, records: list[HotlineRecord] | None = None) -> dict:
    if records is None:
        records = db.scalars(select(HotlineRecord).order_by(HotlineRecord.id.asc())).all()
    else:
        records = sorted(records, key=lambda item: item.id or 0)
    month_labels = _build_month_labels(records)
    legal_domains = FeatureService().list_legal_domains()

    public_interest_counter: dict[str, int] = {}
    legal_domain_counter: dict[str, int] = {name: 0 for name in legal_domains}
    warning_counter: dict[str, int] = {}
    district_counter: dict[str, int] = {}
    difficult_items: list[dict] = []
    area_counter: dict[str, dict] = {
        name: {
            "name": name,
            "count": 0,
            "public_interest_count": 0,
            "warning_count": 0,
            "difficult_count": 0,
            "clusters": {},
            "records": [],
            "month_counts": {label: 0 for label in month_labels},
            "warning_month_counts": {label: 0 for label in month_labels},
        }
        for name in FANGSHAN_AREAS
    }

    for record in records:
        public_interest_counter[record.public_interest_level] = public_interest_counter.get(record.public_interest_level, 0) + 1
        if record.public_interest_level == "公益" and record.legal_domain in legal_domain_counter:
            legal_domain_counter[record.legal_domain] += 1
        warning_counter[record.warning_level] = warning_counter.get(record.warning_level, 0) + 1
        if record.district and (record.public_interest_level == "公益" or record.warning_level in {"中", "高"}):
            district_counter[record.district] = district_counter.get(record.district, 0) + 1
        area_name = _resolve_fangshan_area(record)
        if area_name and area_name in area_counter:
            area_payload = area_counter[area_name]
            bucket = _effective_record_datetime(record).strftime("%Y-%m")
            area_payload["count"] += 1
            if bucket in area_payload["month_counts"]:
                area_payload["month_counts"][bucket] += 1
            if record.public_interest_level == "公益":
                area_payload["public_interest_count"] += 1
            if record.warning_level in {"中", "高"}:
                area_payload["warning_count"] += 1
                if bucket in area_payload["warning_month_counts"]:
                    area_payload["warning_month_counts"][bucket] += 1
            cluster_label = record.point_cluster_label or ((record.aggressive_cluster_json or {}).get("label")) or record.location_text or ""
            if cluster_label:
                area_payload["clusters"][cluster_label] = area_payload["clusters"].get(cluster_label, 0) + 1
        if (
            record.duplicate_count >= 3
            or record.warning_level in {"中", "高"}
            or (record.resolved_status == "未解决" and record.satisfaction_status == "不满意")
        ):
            difficult_item = {
                "ticket_no": record.ticket_no,
                "title": record.title,
                "district": record.district or "待核实",
                "area_name": area_name or "待核实",
                "warning_level": record.warning_level,
                "priority_level": record.priority_level,
                "duplicate_count": record.duplicate_count,
                "duration_days": record.duration_days,
                "legal_domain": _public_domain_label(record.public_interest_level, record.legal_domain),
            }
            difficult_items.append(difficult_item)
            if area_name and area_name in area_counter:
                area_counter[area_name]["difficult_count"] += 1
                area_counter[area_name]["records"].append(difficult_item)

    district_hotspots = [
        {"name": name, "count": count}
        for name, count in sorted(district_counter.items(), key=lambda item: item[1], reverse=True)[:6]
    ]
    difficult_items.sort(key=lambda item: (item["warning_level"], item["duplicate_count"], item["duration_days"]), reverse=True)
    fangshan_map_regions = []
    for name in FANGSHAN_AREAS:
        item = area_counter[name]
        top_clusters = [
            {"label": label, "count": count}
            for label, count in sorted(item["clusters"].items(), key=lambda pair: pair[1], reverse=True)[:5]
        ]
        intensity_score = _build_fangshan_region_intensity(item)
        trend_points = [{"label": label, "count": item["month_counts"][label]} for label in month_labels]
        warning_trend_points = [{"label": label, "count": item["warning_month_counts"][label]} for label in month_labels]
        trend_direction, trend_summary = _summarize_area_trend(trend_points)
        fangshan_map_regions.append(
            {
                "name": name,
                "region_name": name,
                "region_search_keyword": _build_fangshan_region_search_keyword(name),
                "count": item["count"],
                "public_interest_count": item["public_interest_count"],
                "warning_count": item["warning_count"],
                "difficult_count": item["difficult_count"],
                "intensity_score": intensity_score,
                "trend_points": trend_points,
                "warning_trend_points": warning_trend_points,
                "trend_direction": trend_direction,
                "trend_summary": trend_summary,
                "top_clusters": top_clusters,
                "difficult_records": item["records"][:5],
            }
        )

    performance_metrics = _build_performance_anomaly_summary(records)
    duplicate_layer_distribution = _build_duplicate_layer_distribution(records)
    push_task_summary = _build_push_task_summary(db)
    urgent_records = [
        {
            "id": record.id,
            "ticket_no": record.ticket_no,
            "title": record.title,
            "warning_level": record.warning_level,
            "duration_days": record.duration_days,
            "duplicate_count": record.duplicate_count,
            "public_interest_level": record.public_interest_level,
            "legal_domain": _public_domain_label(record.public_interest_level, record.legal_domain),
            "warning_reason_summary": record.warning_reason_summary or "",
        }
        for record in records
        if record.warning_level == "高" or (record.public_interest_level == "公益" and record.duplicate_count >= 3)
    ][:6]

    return {
        "public_interest_distribution": [
            {"name": name or "待复核", "count": count}
            for name, count in sorted(public_interest_counter.items(), key=lambda item: item[1], reverse=True)
        ],
        "legal_domain_distribution": [
            {"name": name, "count": count}
            for name, count in legal_domain_counter.items()
        ],
        "warning_distribution": [
            {"name": name or "无", "count": count}
            for name, count in sorted(warning_counter.items(), key=lambda item: item[1], reverse=True)
        ],
        "duplicate_layer_distribution": duplicate_layer_distribution,
        "performance_anomaly_summary": performance_metrics,
        "trend_series": {
            "months": month_labels,
            "warning": _build_month_series(records, month_labels, predicate=lambda item: item.warning_level in {"中", "高"}),
            "public_interest": _build_month_series(records, month_labels, predicate=lambda item: item.public_interest_level == "公益"),
            "duplicates": _build_month_series(records, month_labels, predicate=lambda item: item.duplicate_count >= 2),
        },
        "domain_trends": _build_domain_trends(records, month_labels),
        "district_hotspots": district_hotspots,
        "fangshan_map_regions": fangshan_map_regions,
        "difficult_records": difficult_items[:6],
        "urgent_records": urgent_records,
        "push_task_summary": push_task_summary,
        "special_report": _build_special_report_payload(records, month_labels),
    }


def _build_duplicate_layer_distribution(records: list[HotlineRecord]) -> list[dict]:
    counter: dict[str, int] = {}
    for record in records:
        label = record.duplicate_level or "无"
        counter[label] = counter.get(label, 0) + 1
    ordered_labels = ["强重复", "弱重复", "同区域同类高频", "无"]
    return [
        {"name": label, "count": counter.get(label, 0)}
        for label in ordered_labels
        if label in counter or label != "无" or counter.get(label, 0) > 0
    ]


def _build_performance_anomaly_summary(records: list[HotlineRecord]) -> dict:
    bucket_stats: dict[tuple[str, str], dict[str, int]] = {}
    for record in records:
        bucket = bucket_stats.setdefault(
            (record.district or "未识别区域", _domain_bucket_label(record.public_interest_level, record.legal_domain)),
            {"total": 0, "resolved": 0, "dissatisfied": 0, "timeout": 0, "anomaly": 0},
        )
        bucket["total"] += 1
        if record.resolved_status == "已解决":
            bucket["resolved"] += 1
        if record.satisfaction_status == "不满意":
            bucket["dissatisfied"] += 1
        if record.response_status == "超时":
            bucket["timeout"] += 1
        if (record.performance_anomaly_level or "无") in {"中", "高"}:
            bucket["anomaly"] += 1

    ranking: list[dict] = []
    for (district, domain), stats in bucket_stats.items():
        total = stats["total"] or 1
        resolution_rate = stats["resolved"] / total
        ranking.append(
            {
                "district": district,
                "legal_domain": domain,
                "total": stats["total"],
                "resolution_rate": round(resolution_rate, 4),
                "dissatisfaction_rate": round(stats["dissatisfied"] / total, 4),
                "timeout_rate": round(stats["timeout"] / total, 4),
                "anomaly_count": stats["anomaly"],
            }
        )
    ranking.sort(
        key=lambda item: (
            -item["anomaly_count"],
            item["resolution_rate"],
            -item["dissatisfaction_rate"],
        )
    )
    level_counter: dict[str, int] = {"高": 0, "中": 0, "低": 0, "无": 0}
    for record in records:
        level_counter[record.performance_anomaly_level or "无"] = level_counter.get(record.performance_anomaly_level or "无", 0) + 1
    return {
        "level_distribution": [
            {"name": name, "count": count}
            for name, count in level_counter.items()
            if count
        ],
        "ranking": ranking[:6],
    }


def _build_push_task_summary(db: Session) -> dict:
    items = list_push_tasks(db, limit=10)
    serialized = [serialize_push_task(item) for item in items]
    pending = [item for item in serialized if item["status"] in {"pending", "queued"}]
    failed = [item for item in serialized if item["status"] == "failed"]
    delivered = [item for item in serialized if item["status"] == "delivered"]
    return {
        "recent_tasks": serialized[:6],
        "pending_count": len(pending),
        "failed_count": len(failed),
        "delivered_count": len(delivered),
    }


def _build_special_report_payload(records: list[HotlineRecord], month_labels: list[str]) -> dict:
    public_interest_count = sum(1 for record in records if record.public_interest_level == "公益")
    high_frequency_count = sum(1 for record in records if record.duplicate_count >= 3)
    high_warning_count = sum(1 for record in records if record.warning_level == "高")
    medium_warning_count = sum(1 for record in records if record.warning_level == "中")
    anomaly_count = sum(1 for record in records if (record.performance_anomaly_level or "无") in {"中", "高"})
    return {
        "reporting_period": f"{month_labels[0]} 至 {month_labels[-1]}" if month_labels else "",
        "high_frequency_count": high_frequency_count,
        "public_interest_count": public_interest_count,
        "high_warning_count": high_warning_count,
        "medium_warning_count": medium_warning_count,
        "performance_anomaly_count": anomaly_count,
        "summary_lines": [
            f"共识别公益属性工单 {public_interest_count} 条。",
            f"重复投诉达到3次及以上的工单 {high_frequency_count} 条。",
            f"中高等级预警工单 {high_warning_count + medium_warning_count} 条，其中高等级 {high_warning_count} 条。",
            f"识别到行政机关履职异常工单 {anomaly_count} 条。",
        ],
    }


def build_special_report(db: Session, period: str = "monthly") -> dict:
    """Aggregate the latest 1 (monthly) or 3 (quarterly) months of records."""
    records = db.scalars(select(HotlineRecord).order_by(HotlineRecord.id.asc())).all()
    month_labels = _build_month_labels(records, limit=3 if period == "quarterly" else 1)
    selected_months = set(month_labels)
    filtered = [
        record
        for record in records
        if _effective_record_datetime(record).strftime("%Y-%m") in selected_months
    ]
    payload = _build_special_report_payload(filtered, month_labels)
    payload["period"] = period
    payload["months"] = month_labels
    payload["urgent_records"] = [
        {
            "ticket_no": record.ticket_no,
            "title": record.title,
            "district": record.district or "待核实",
            "warning_level": record.warning_level,
            "legal_domain": _public_domain_label(record.public_interest_level, record.legal_domain),
            "duration_days": record.duration_days,
        }
        for record in filtered
        if record.warning_level == "高"
    ][:8]
    return payload


def build_dashboard(
    db: Session,
    *,
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
) -> dict:
    base_query = _apply_record_filters(
        select(HotlineRecord),
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
    filtered_records = db.scalars(base_query.order_by(HotlineRecord.id.desc())).all()

    total_records = len(filtered_records)
    screened_records = sum(1 for item in filtered_records if item.status == "已筛查")
    procuratorial_records = sum(1 for item in filtered_records if item.is_procuratorial)
    high_risk_records = sum(1 for item in filtered_records if item.risk_level == "高")
    duplicate_records = sum(1 for item in filtered_records if item.is_duplicate)
    location_records = sum(1 for item in filtered_records if item.has_location)

    source_counter: dict[str, int] = {}
    category_counter: dict[str, int] = {}
    risk_counter: dict[str, int] = {}
    review_counter: dict[str, int] = {}
    focus_candidates = [item for item in filtered_records if item.has_location][:200]
    for item in filtered_records:
        source_counter[item.source or "未知来源"] = source_counter.get(item.source or "未知来源", 0) + 1
        category_counter[item.category or "未分类"] = category_counter.get(item.category or "未分类", 0) + 1
        risk_counter[item.risk_level or "待评估"] = risk_counter.get(item.risk_level or "待评估", 0) + 1
        review_counter[item.review_status or "待标注"] = review_counter.get(item.review_status or "待标注", 0) + 1

    source_rows = sorted(source_counter.items(), key=lambda item: item[1], reverse=True)
    category_rows = sorted(category_counter.items(), key=lambda item: item[1], reverse=True)
    risk_rows = sorted(risk_counter.items(), key=lambda item: item[1], reverse=True)
    review_rows = sorted(review_counter.items(), key=lambda item: item[1], reverse=True)
    focus_counter: dict[str, int] = {}
    for item in focus_candidates:
        label = item.point_cluster_label or item.location_text or ""
        if not label:
            continue
        focus_counter[label] = focus_counter.get(label, 0) + 1
    focus_rows = sorted(
        [{"name": label, "count": count} for label, count in focus_counter.items() if count > 1],
        key=lambda item: item["count"],
        reverse=True,
    )[:5]
    recent_records = filtered_records[:8]
    recent_exports = db.scalars(select(ExportRecord).order_by(ExportRecord.id.desc()).limit(5)).all()
    recent_jobs = db.scalars(select(ScreeningJobRecord).order_by(ScreeningJobRecord.id.desc()).limit(3)).all()

    analysis_payload = build_analysis_payload(db, records=filtered_records)

    return {
        "total_records": total_records,
        "screened_records": screened_records,
        "procuratorial_records": procuratorial_records,
        "high_risk_records": high_risk_records,
        "duplicate_records": duplicate_records,
        "location_records": location_records,
        "source_distribution": [{"name": row[0], "count": row[1]} for row in source_rows],
        "category_distribution": [{"name": row[0], "count": row[1]} for row in category_rows],
        "risk_distribution": [{"name": row[0], "count": row[1]} for row in risk_rows],
        "review_distribution": [{"name": row[0], "count": row[1]} for row in review_rows],
        "focus_locations": focus_rows,
        "recent_records": [serialize_record(item) for item in recent_records],
        "recent_exports": [serialize_export_record(item) for item in recent_exports],
        "recent_jobs": [serialize_screening_job(item) for item in recent_jobs],
        **analysis_payload,
    }


def list_hotline_records(
    db: Session,
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
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), settings.max_query_page_size)
    query = _apply_record_filters(
        select(HotlineRecord),
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
    total = _count_query(db, query)
    items = db.scalars(
        query.order_by(HotlineRecord.id.desc()).offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
    ).all()
    pages = max(1, math.ceil(total / safe_page_size)) if total else 1
    return {
        "items": [serialize_record(item) for item in items],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "pages": pages,
    }


def get_record_by_id(db: Session, record_id: int | None) -> HotlineRecord | None:
    if not record_id:
        return None
    return db.get(HotlineRecord, record_id)


def create_hotline_record(db: Session, payload: dict) -> HotlineRecord:
    status_fields = _derive_status_fields(
        resolved_text=str(payload.get("resolved_status", "")),
        satisfaction_text=str(payload.get("satisfaction_status", "")),
        handling_result=str((payload.get("raw_payload_json") or {}).get("办理结果", "")),
        reply_content=str((payload.get("raw_payload_json") or {}).get("回复内容", "")),
        complaint_text=str(payload.get("complaint_text", "")),
    )
    payload.setdefault("resolved_status", status_fields["resolved_status"])
    payload.setdefault("satisfaction_status", status_fields["satisfaction_status"])
    payload.setdefault("response_status", status_fields["response_status"])
    first_seen_at, last_seen_at = _build_record_timeline(str(payload.get("event_time", "")))
    payload.setdefault("first_seen_at", first_seen_at)
    payload.setdefault("last_seen_at", last_seen_at)
    record = HotlineRecord(**payload)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def import_demo_records(db: Session) -> list[HotlineRecord]:
    demo_payloads = [
        {
            "ticket_no": "DEMO-BATCH-01",
            "source": "12345",
            "channel": "批量导入",
            "title": "工地欠薪批量样本",
            "complainant_name": "赵师傅",
            "complainant_phone": "13810000001",
            "district": "房山区",
            "location_text": "房山区青龙湖项目工地",
            "event_time": "2026-04-08 09:10",
            "complaint_text": "青龙湖项目工地拖欠6名工人两个月工资共4万元。",
        },
        {
            "ticket_no": "DEMO-BATCH-02",
            "source": "12345",
            "channel": "批量导入",
            "title": "环境治理批量样本",
            "complainant_name": "周女士",
            "complainant_phone": "13810000002",
            "district": "房山区",
            "location_text": "房山区拱辰街道南关市场",
            "event_time": "2026-04-08 11:20",
            "complaint_text": "南关市场周边长期油烟扰民并伴随垃圾堆放，已有多人投诉。",
        },
        {
            "ticket_no": "DEMO-BATCH-03",
            "source": "街道综治",
            "channel": "批量导入",
            "title": "行政监督批量样本",
            "complainant_name": "企业联系人",
            "complainant_phone": "13810000003",
            "district": "房山区",
            "location_text": "房山区燕山园区",
            "event_time": "2026-04-08 15:30",
            "complaint_text": "燕山园区企业反映处罚太重、同案不同罚，执法解释前后不一致。",
        },
    ]

    created: list[HotlineRecord] = []
    for payload in demo_payloads:
        record = HotlineRecord(**payload, raw_payload_json=payload)
        db.add(record)
        created.append(record)
    db.commit()
    for record in created:
        db.refresh(record)
    return created


def _create_screening_job(
    db: Session,
    *,
    total_records: int,
    batch_size: int,
    only_pending: bool,
    record_ids: list[int] | None,
    versions: dict[str, str],
) -> ScreeningJobRecord:
    job = ScreeningJobRecord(
        job_name="batch-screening",
        status="running",
        total_records=total_records,
        processed_records=0,
        batch_size=batch_size,
        only_pending=only_pending,
        record_ids_json=record_ids or [],
        screening_version=versions["screening_version"],
        model_version=versions["model_version"],
        feature_version=versions["feature_version"],
        summary_json={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_screening(
    db: Session,
    record_ids: list[int] | None = None,
    only_pending: bool = True,
    batch_size: int | None = None,
) -> dict:
    from huxin_platform.services.screening_service import ScreeningService
    from huxin_platform.services.point_aggregation_service import PointAggregationService
    from huxin_platform.services.semantic_search_service import SemanticSearchService

    service = ScreeningService()
    point_aggregation_service = PointAggregationService()
    semantic_search_service = SemanticSearchService()
    safe_batch_size = batch_size or settings.screening_batch_size
    target_query = _apply_record_filters(
        select(HotlineRecord),
        record_ids=record_ids,
        only_pending=only_pending,
    )
    total_targets = _count_query(db, target_query)
    versions = service.get_runtime_versions()
    job = _create_screening_job(
        db,
        total_records=total_targets,
        batch_size=safe_batch_size,
        only_pending=only_pending,
        record_ids=record_ids,
        versions=versions,
    )
    if total_targets == 0:
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.summary_json = {"message": "当前没有需要筛查的工单。"}
        db.add(job)
        db.commit()
        return {
            "job_id": job.id,
            "screened_count": 0,
            "high_risk_count": 0,
            "procuratorial_count": 0,
            "batch_size": safe_batch_size,
            "model_version": versions["model_version"],
        }

    duplicate_query = _apply_record_filters(select(HotlineRecord), record_ids=record_ids, only_pending=None)
    duplicate_counts: dict[str, int] = {}
    duplicate_timelines: dict[str, dict[str, datetime | None]] = {}
    weak_match_counts: dict[str, int] = {}
    person_match_counts: dict[str, int] = {}
    last_seen_id = 0
    while True:
        batch_rows = db.scalars(
            duplicate_query.where(HotlineRecord.id > last_seen_id).order_by(HotlineRecord.id.asc()).limit(safe_batch_size)
        ).all()
        if not batch_rows:
            break
        for item in batch_rows:
            signals = service.build_duplicate_signals(
                item.complaint_text,
                item.location_text,
                item.district,
                complainant_name=item.complainant_name,
                complainant_phone=item.complainant_phone,
            )
            composite_key = signals["composite_key"]
            duplicate_counts[composite_key] = duplicate_counts.get(composite_key, 0) + 1
            weak_match_counts[signals["weak_key"]] = weak_match_counts.get(signals["weak_key"], 0) + 1
            person_match_counts[signals["person_key"]] = person_match_counts.get(signals["person_key"], 0) + 1
            event_dt = _parse_datetime(item.event_time) or item.created_at
            timeline = duplicate_timelines.setdefault(composite_key, {"first_seen_at": event_dt, "last_seen_at": event_dt})
            if event_dt and (timeline["first_seen_at"] is None or event_dt < timeline["first_seen_at"]):
                timeline["first_seen_at"] = event_dt
            if event_dt and (timeline["last_seen_at"] is None or event_dt > timeline["last_seen_at"]):
                timeline["last_seen_at"] = event_dt
        last_seen_id = batch_rows[-1].id

    high_risk_count = 0
    procuratorial_count = 0
    processed_count = 0
    last_target_id = 0

    try:
        while True:
            batch_items = db.scalars(
                target_query.where(HotlineRecord.id > last_target_id).order_by(HotlineRecord.id.asc()).limit(safe_batch_size)
            ).all()
            if not batch_items:
                break

            for item in batch_items:
                signals = service.build_duplicate_signals(
                    item.complaint_text,
                    item.location_text,
                    item.district,
                    complainant_name=item.complainant_name,
                    complainant_phone=item.complainant_phone,
                )
                composite_key = signals["composite_key"]
                duplicate_count = duplicate_counts.get(composite_key, 1)
                analyzed = service.analyze_record(
                    complaint_text=item.complaint_text,
                    location_text=item.location_text,
                    district=item.district,
                    duplicate_count=duplicate_count,
                    duplicate_group=composite_key,
                    resolved_status=item.resolved_status,
                    satisfaction_status=item.satisfaction_status,
                    response_status=item.response_status,
                    first_seen_at=(duplicate_timelines.get(composite_key) or {}).get("first_seen_at"),
                    last_seen_at=(duplicate_timelines.get(composite_key) or {}).get("last_seen_at"),
                    complainant_name=item.complainant_name,
                    complainant_phone=item.complainant_phone,
                    weak_match_count=weak_match_counts.get(signals["weak_key"], 0),
                    person_match_count=person_match_counts.get(signals["person_key"], 0),
                )
                for key, value in analyzed.items():
                    setattr(item, key, value)
                item.screened_at = datetime.utcnow()
                db.add(item)
                if item.risk_level == "高":
                    high_risk_count += 1
                if item.is_procuratorial:
                    procuratorial_count += 1

            processed_count += len(batch_items)
            job.processed_records = processed_count
            job.high_risk_count = high_risk_count
            job.procuratorial_count = procuratorial_count
            job.summary_json = {
                "progress": round(processed_count / total_targets, 4),
                "batch_size": safe_batch_size,
            }
            last_target_id = batch_items[-1].id
            db.add(job)
            db.commit()

        all_records = db.scalars(select(HotlineRecord).order_by(HotlineRecord.id.asc())).all()
        annotate_performance_anomalies(all_records)
        semantic_search_service.ensure_record_features(db, all_records)
        cluster_payload = point_aggregation_service.refresh_clusters(all_records)
        for item in all_records:
            db.add(item)
        db.commit()

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.summary_json = {
            "progress": 1.0,
            "screened_count": processed_count,
            "high_risk_count": high_risk_count,
            "procuratorial_count": procuratorial_count,
            "stable_cluster_count": len(cluster_payload["stable_clusters"]),
            "aggressive_cluster_count": len(cluster_payload["aggressive_clusters"]),
        }
        db.add(job)
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(ScreeningJobRecord, job.id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.add(job)
            db.commit()
        raise

    return {
        "job_id": job.id,
        "screened_count": processed_count,
        "high_risk_count": high_risk_count,
        "procuratorial_count": procuratorial_count,
        "batch_size": safe_batch_size,
        "model_version": versions["model_version"],
    }


def update_hotline_record_review(db: Session, record: HotlineRecord, payload: dict) -> HotlineRecord:
    for key, value in payload.items():
        setattr(record, key, value)
    record.reviewed_at = datetime.utcnow()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_external_sync_record(db: Session, payload: dict) -> ExternalSyncRecord:
    record = ExternalSyncRecord(**payload)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_external_sync_record_by_id(db: Session, record_id: int | None) -> ExternalSyncRecord | None:
    if not record_id:
        return None
    return db.get(ExternalSyncRecord, record_id)


def get_external_sync_record_by_raw_id(
    db: Session,
    source_system: str,
    raw_external_id: str | None,
) -> ExternalSyncRecord | None:
    if not raw_external_id:
        return None
    query = (
        select(ExternalSyncRecord)
        .where(
            ExternalSyncRecord.source_system == source_system,
            ExternalSyncRecord.raw_external_id == raw_external_id,
        )
        .order_by(ExternalSyncRecord.id.desc())
    )
    return db.scalars(query).first()


def update_external_sync_record(db: Session, record: ExternalSyncRecord, payload: dict) -> ExternalSyncRecord:
    for key, value in payload.items():
        setattr(record, key, value)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_export_record(db: Session, payload: dict) -> ExportRecord:
    record = ExportRecord(**payload)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_llm_log(db: Session, payload: dict) -> LLMCallLog:
    log = LLMCallLog(**payload)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def build_export_file(
    db: Session,
    category: str = "",
    risk_level: str = "",
    handling_status: str = "",
) -> dict:
    export_dir = Path(settings.exports_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"hotline_screening_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    file_path = export_dir / file_name
    preview_lines: list[str] = []
    preview_limit = settings.export_preview_rows

    query = _apply_record_filters(
        select(HotlineRecord),
        category=category,
        risk_level=risk_level,
        handling_status=handling_status,
    )
    total_count = _count_query(db, query)
    exported_at = datetime.utcnow()
    last_id = 0

    with file_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        header = [
            "工单编号",
            "来源",
            "类别",
            "法定领域",
            "公益属性",
            "风险等级",
            "优先级",
            "预警等级",
            "是否涉检",
            "是否重复",
            "是否有点位",
            "人工标注",
            "办理状态",
            "点位",
            "筛查摘要",
        ]
        writer.writerow(header)
        preview_lines.append(",".join(header))

        while True:
            batch_rows = db.scalars(
                query.where(HotlineRecord.id > last_id).order_by(HotlineRecord.id.asc()).limit(settings.export_batch_size)
            ).all()
            if not batch_rows:
                break
            for row in batch_rows:
                csv_row = [
                    row.ticket_no,
                    row.source,
                    row.category,
                    _public_domain_label(row.public_interest_level, row.legal_domain),
                    row.public_interest_level,
                    row.risk_level,
                    row.priority_level,
                    row.warning_level,
                    "是" if row.is_procuratorial else "否",
                    "是" if row.is_duplicate else "否",
                    "是" if row.has_location else "否",
                    row.manual_label or "待标注",
                    row.handling_status,
                    row.location_text or "",
                    row.screening_summary or "",
                ]
                writer.writerow(csv_row)
                if len(preview_lines) <= preview_limit:
                    preview_lines.append(",".join(str(item) for item in csv_row))
                row.exported_at = exported_at
                db.add(row)
            last_id = batch_rows[-1].id
            db.commit()

    create_export_record(
        db,
        {
            "export_scope": "筛查台账导出",
            "export_format": "csv",
            "item_count": total_count,
            "file_name": file_name,
            "remark": "平台按批次导出生成，可承载更大规模数据。",
        },
    )

    if total_count > preview_limit:
        preview_lines.append(f"... 共 {total_count} 条，预览仅展示前 {preview_limit} 条，完整文件已写入 {file_path}")

    return {
        "file_name": file_name,
        "file_path": str(file_path),
        "content": "\n".join(preview_lines),
        "item_count": total_count,
    }


def annotate_performance_anomalies(records: list[HotlineRecord]) -> dict:
    """Aggregate resolution / satisfaction / response metrics per district+domain
    and surface a per-record `performance_anomaly_level` so the warning panel can
    explain administrative履职 异常 inline with each record."""
    bucket_stats: dict[tuple[str, str], dict[str, int]] = {}
    for item in records:
        district = item.district or "未识别区域"
        domain = _domain_bucket_label(item.public_interest_level, item.legal_domain)
        bucket = bucket_stats.setdefault(
            (district, domain),
            {"total": 0, "resolved": 0, "unresolved": 0, "satisfied": 0, "dissatisfied": 0, "timeout": 0, "responded": 0},
        )
        bucket["total"] += 1
        if item.resolved_status == "已解决":
            bucket["resolved"] += 1
        elif item.resolved_status == "未解决":
            bucket["unresolved"] += 1
        if item.satisfaction_status == "满意":
            bucket["satisfied"] += 1
        elif item.satisfaction_status == "不满意":
            bucket["dissatisfied"] += 1
        if item.response_status == "已响应":
            bucket["responded"] += 1
        elif item.response_status == "超时":
            bucket["timeout"] += 1

    bucket_metrics: dict[tuple[str, str], dict] = {}
    for key, stats in bucket_stats.items():
        total = stats["total"] or 1
        bucket_metrics[key] = {
            "total": stats["total"],
            "resolution_rate": round(stats["resolved"] / total, 4),
            "dissatisfaction_rate": round(stats["dissatisfied"] / total, 4),
            "timeout_rate": round(stats["timeout"] / total, 4),
            "unresolved_rate": round(stats["unresolved"] / total, 4),
        }

    for item in records:
        key = (item.district or "未识别区域", _domain_bucket_label(item.public_interest_level, item.legal_domain))
        metrics = bucket_metrics.get(key)
        anomalies: list[str] = []
        if metrics and metrics["total"] >= 5:
            if metrics["resolution_rate"] <= 0.3:
                anomalies.append(f"该区域同领域解决率仅 {round(metrics['resolution_rate'] * 100, 1)}%")
            if metrics["dissatisfaction_rate"] >= 0.5:
                anomalies.append(f"群众不满意比例达到 {round(metrics['dissatisfaction_rate'] * 100, 1)}%")
            if metrics["timeout_rate"] >= 0.4:
                anomalies.append(f"响应超时比例达到 {round(metrics['timeout_rate'] * 100, 1)}%")
            if metrics["unresolved_rate"] >= 0.6 and metrics["total"] >= 8:
                anomalies.append(f"长期未解决占比达到 {round(metrics['unresolved_rate'] * 100, 1)}%")

        # An individual record only carries the bucket-level anomaly when it itself
        # exhibits unresolved/dissatisfied/timeout signals, so we don't paint every
        # record in a bad bucket as 异常.
        record_signals = sum(
            1
            for flag in (
                item.resolved_status == "未解决",
                item.satisfaction_status == "不满意",
                item.response_status == "超时",
            )
            if flag
        )

        if not anomalies or record_signals == 0:
            level = "无"
            anomalies = []
        elif len(anomalies) >= 3 and record_signals >= 2:
            level = "高"
        elif len(anomalies) >= 2 and record_signals >= 1:
            level = "中"
        else:
            level = "低"
        item.performance_anomaly_level = level
        item.performance_anomaly_reasons_json = anomalies[:5]

    return {
        "bucket_metrics": [
            {"district": district, "legal_domain": domain, **metrics}
            for (district, domain), metrics in bucket_metrics.items()
        ],
    }


def list_push_tasks(db: Session, limit: int = 20) -> list[PushTaskRecord]:
    return list(
        db.scalars(select(PushTaskRecord).order_by(PushTaskRecord.id.desc()).limit(limit)).all()
    )


def create_push_task(db: Session, payload: dict) -> PushTaskRecord:
    record = PushTaskRecord(**payload)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_push_task(db: Session, record: PushTaskRecord, payload: dict) -> PushTaskRecord:
    for key, value in payload.items():
        setattr(record, key, value)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_push_task_by_id(db: Session, record_id: int | None) -> PushTaskRecord | None:
    if not record_id:
        return None
    return db.get(PushTaskRecord, record_id)


def serialize_push_task(item: PushTaskRecord) -> dict:
    return {
        "id": item.id,
        "push_type": item.push_type,
        "trigger_mode": item.trigger_mode,
        "status": item.status,
        "target_endpoint": item.target_endpoint or "",
        "item_count": item.item_count,
        "retry_count": item.retry_count,
        "payload": item.payload_json or {},
        "response": item.response_json or {},
        "last_error": item.last_error or "",
        "created_at": _format_datetime(item.created_at),
        "delivered_at": _format_datetime(item.delivered_at),
    }


def serialize_record(item: HotlineRecord, search_explanation: dict | None = None) -> dict:
    structured_fields = item.structured_fields_json or {}
    return {
        "id": item.id,
        "ticket_no": item.ticket_no,
        "source": item.source,
        "channel": item.channel,
        "title": item.title,
        "complainant_name": item.complainant_name or "匿名",
        "complainant_phone": item.complainant_phone or "未留存",
        "district": item.district or "",
        "location_text": item.location_text or "",
        "event_time": item.event_time or "",
        "complaint_text": item.complaint_text,
        "status": item.status,
        "has_location": item.has_location,
        "is_duplicate": item.is_duplicate,
        "duplicate_group": item.duplicate_group or "",
        "duplicate_count": item.duplicate_count,
        "duplicate_level": item.duplicate_level or "无",
        "duplicate_reasons": item.duplicate_reasons_json or [],
        "category": item.category,
        "subcategory": item.subcategory or "",
        "procuratorial_type": item.procuratorial_type,
        "is_procuratorial": item.is_procuratorial,
        "risk_level": item.risk_level,
        "priority_level": item.priority_level,
        "priority_reason": item.priority_reason or "",
        "public_interest_level": item.public_interest_level,
        "public_interest_score": item.public_interest_score,
        "public_interest_reasons": item.public_interest_reasons_json or [],
        "public_interest_evidence": item.public_interest_evidence_json or {},
        "legal_domain": item.legal_domain if item.public_interest_level != "私益" else "",
        "domain_confidence": (item.domain_confidence or 0.0) if item.public_interest_level != "私益" else 0.0,
        "domain_tags": item.domain_tags_json if item.public_interest_level != "私益" else [],
        "domain_candidates": item.domain_candidates_json if item.public_interest_level != "私益" else [],
        "domain_conflict_flags": item.domain_conflict_flags_json if item.public_interest_level != "私益" else [],
        "resolved_status": item.resolved_status,
        "satisfaction_status": item.satisfaction_status,
        "response_status": item.response_status,
        "warning_level": item.warning_level,
        "warning_flags": item.warning_flags_json or [],
        "warning_reason_summary": item.warning_reason_summary or "",
        "performance_anomaly_level": item.performance_anomaly_level or "无",
        "performance_anomaly_reasons": item.performance_anomaly_reasons_json or [],
        "duration_days": item.duration_days,
        "screening_version": item.screening_version,
        "model_version": item.model_version or "",
        "feature_version": item.feature_version or "",
        "screening_confidence": item.screening_confidence,
        "matched_rules": item.matched_rules_json or [],
        "structured_fields": structured_fields,
        "ml_prediction": item.ml_prediction_json or {},
        "dl_prediction": item.dl_prediction_json or {},
        "ensemble_prediction": item.ensemble_prediction_json or {},
        "semantic_keywords": item.semantic_keywords_json or {},
        "normalized_point": item.normalized_point_json or {},
        "point_cluster_id": item.point_cluster_id or "",
        "point_cluster_label": item.point_cluster_label or "",
        "aggressive_cluster": item.aggressive_cluster_json or {},
        "screening_summary": item.screening_summary or "",
        "review_status": item.review_status,
        "manual_label": item.manual_label or "待标注",
        "handling_status": item.handling_status,
        "review_comment": item.review_comment or "",
        "search_explanation": search_explanation or {},
        "first_seen_at": _format_datetime(item.first_seen_at),
        "last_seen_at": _format_datetime(item.last_seen_at),
        "screened_at": _format_datetime(item.screened_at),
        "reviewed_at": _format_datetime(item.reviewed_at),
        "exported_at": _format_datetime(item.exported_at),
        "created_at": _format_datetime(item.created_at),
        "updated_at": _format_datetime(item.updated_at),
    }


def serialize_export_record(item: ExportRecord) -> dict:
    return {
        "id": item.id,
        "export_scope": item.export_scope,
        "export_format": item.export_format,
        "item_count": item.item_count,
        "file_name": item.file_name,
        "remark": item.remark or "",
        "created_at": _format_datetime(item.created_at),
    }


def serialize_screening_job(item: ScreeningJobRecord) -> dict:
    return {
        "id": item.id,
        "job_name": item.job_name,
        "status": item.status,
        "total_records": item.total_records,
        "processed_records": item.processed_records,
        "high_risk_count": item.high_risk_count,
        "procuratorial_count": item.procuratorial_count,
        "batch_size": item.batch_size,
        "screening_version": item.screening_version,
        "model_version": item.model_version or "",
        "feature_version": item.feature_version or "",
        "summary": item.summary_json or {},
        "error_message": item.error_message or "",
        "started_at": _format_datetime(item.started_at),
        "completed_at": _format_datetime(item.completed_at),
    }


def serialize_model_artifact(item: ModelArtifactRecord) -> dict:
    return {
        "id": item.id,
        "model_type": item.model_type,
        "model_name": item.model_name,
        "model_version": item.model_version,
        "file_path": item.file_path,
        "is_active": item.is_active,
        "metrics": item.metrics_json or {},
        "extra": item.extra_json or {},
        "created_at": _format_datetime(item.created_at),
    }
