from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from huxin_platform.core.config import settings
from huxin_platform.models.entities import HotlineRecord, PushTaskRecord
from huxin_platform.repositories.platform_repository import (
    create_external_sync_record,
    create_push_task,
    get_external_sync_record_by_raw_id,
    get_push_task_by_id,
    list_push_tasks,
    serialize_push_task,
    update_external_sync_record,
    update_push_task,
)


@dataclass(frozen=True)
class SourceRuntimeConfig:
    source_system: str
    mode: str
    endpoint: str
    auth_type: str
    token: str
    app_key: str
    app_secret: str
    http_method: str
    pull_strategy: str
    timeout_seconds: int


class IntegrationService:
    """Connector layer for demo and future hotline source systems."""

    def __init__(self) -> None:
        self._source_labels = {
            "12345": "12345",
            "街道综治": "street",
            "检察业务": "procuratorate",
        }

    def list_sources(self) -> list[dict]:
        return [
            self._serialize_source(self._build_source_config("12345")),
            self._serialize_source(self._build_source_config("街道综治")),
            self._serialize_source(self._build_source_config("检察业务")),
        ]

    def pull_source(self, db: Session, source_system: str) -> dict:
        config = self._build_source_config(source_system)
        normalized_result = self._fetch_source_payload(config)
        normalized_payload = normalized_result["payload"]
        normalized_summary = self._build_summary(normalized_payload)

        record = self._upsert_sync_record(
            db,
            config=config,
            raw_external_id=normalized_result["external_id"],
            raw_payload=normalized_result["raw_payload"],
            normalized_payload=normalized_payload,
            normalized_summary=normalized_summary,
            sync_status=normalized_result["sync_status"],
        )

        return {
            "record_id": record.id,
            "source_system": source_system,
            "mode": config.mode,
            "sync_status": record.sync_status,
            "payload": normalized_payload,
            "summary": normalized_summary,
            "external_id": normalized_result["external_id"],
            "error_message": record.error_message,
        }

    def build_push_payload(self, db: Session, push_type: str = "daily") -> dict:
        from huxin_platform.repositories.platform_repository import build_analysis_payload

        analysis_payload = build_analysis_payload(db)
        report = analysis_payload["special_report"]
        return {
            "push_type": push_type,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": report["summary_lines"],
            "high_warning_count": report["high_warning_count"],
            "public_interest_count": report["public_interest_count"],
            "high_frequency_count": report["high_frequency_count"],
            "difficult_records": analysis_payload["difficult_records"][:5],
            "status": "已生成推送载荷，待接入真实推送通道",
        }

    # ------------ Push lifecycle (T+1 batch / emergency / retry) ------------

    PUSH_DAILY = "daily"
    PUSH_WEEKLY = "weekly"
    PUSH_EMERGENCY = "emergency"

    def list_push_tasks(self, db: Session, limit: int = 20) -> list[dict]:
        return [serialize_push_task(item) for item in list_push_tasks(db, limit=limit)]

    def enqueue_batch_push(
        self,
        db: Session,
        *,
        push_type: str = "daily",
        trigger_mode: str = "manual",
        target_endpoint: str | None = None,
    ) -> dict:
        """Build a batch payload (T+1 daily or weekly) and persist it as a pending task."""
        if push_type not in (self.PUSH_DAILY, self.PUSH_WEEKLY):
            raise ValueError("push_type 仅支持 daily 或 weekly")
        records = self._collect_batch_records(db, push_type=push_type)
        payload = self._build_batch_payload(db, push_type=push_type, records=records)
        task = create_push_task(
            db,
            {
                "push_type": push_type,
                "trigger_mode": trigger_mode,
                "status": "queued",
                "target_endpoint": target_endpoint or settings.push_target_endpoint,
                "item_count": len(records),
                "payload_json": payload,
            },
        )
        return serialize_push_task(task)

    def enqueue_emergency_push(
        self,
        db: Session,
        *,
        record_ids: list[int],
        trigger_mode: str = "manual",
        target_endpoint: str | None = None,
    ) -> dict:
        """Push a hand-picked set of urgent clues immediately (still goes through retry pipeline)."""
        if not record_ids:
            raise ValueError("record_ids 不能为空")
        records = list(
            db.scalars(select(HotlineRecord).where(HotlineRecord.id.in_(record_ids))).all()
        )
        if not records:
            raise ValueError("未找到指定的工单，无法构造紧急推送载荷")
        payload = self._build_emergency_payload(records)
        task = create_push_task(
            db,
            {
                "push_type": self.PUSH_EMERGENCY,
                "trigger_mode": trigger_mode,
                "status": "queued",
                "target_endpoint": target_endpoint or settings.push_target_endpoint,
                "item_count": len(records),
                "payload_json": payload,
            },
        )
        return serialize_push_task(task)

    def deliver_push_task(self, db: Session, task_id: int) -> dict:
        """Send a queued task. Falls back to a simulated delivery when no real endpoint is configured.
        On failure increments retry_count so it can be retried later via the same endpoint."""
        task = get_push_task_by_id(db, task_id)
        if not task:
            raise ValueError("推送任务不存在")
        if task.status == "delivered":
            return serialize_push_task(task)

        endpoint = task.target_endpoint or settings.push_target_endpoint
        delivered_payload = task.payload_json or {}
        try:
            response_payload = self._deliver_payload(endpoint, delivered_payload)
            updated = update_push_task(
                db,
                task,
                {
                    "status": "delivered",
                    "response_json": response_payload,
                    "delivered_at": datetime.utcnow(),
                    "last_error": None,
                },
            )
            return serialize_push_task(updated)
        except Exception as exc:  # noqa: BLE001
            updated = update_push_task(
                db,
                task,
                {
                    "status": "failed",
                    "retry_count": (task.retry_count or 0) + 1,
                    "last_error": str(exc)[:500],
                },
            )
            return serialize_push_task(updated)

    def deliver_pending_tasks(self, db: Session, *, max_tasks: int = 10) -> list[dict]:
        pending = [
            task
            for task in db.scalars(
                select(PushTaskRecord).where(PushTaskRecord.status.in_(["queued", "failed"]))
                .order_by(PushTaskRecord.id.asc())
                .limit(max_tasks)
            ).all()
        ]
        return [self.deliver_push_task(db, task.id) for task in pending]

    def _deliver_payload(self, endpoint: str | None, payload: dict) -> dict:
        if not endpoint:
            # Simulated delivery so the demo retains a closed loop without a real downstream system.
            return {
                "ok": True,
                "delivered_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "channel": "simulated",
                "ack_id": f"SIM-{int(datetime.utcnow().timestamp())}",
                "items": int(payload.get("item_count", 0) or 0),
            }
        timeout = settings.integration_timeout_seconds or 10
        with httpx.Client(timeout=timeout) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
        try:
            return response.json()
        except Exception:  # noqa: BLE001
            return {"ok": True, "raw": response.text[:1000]}

    def _collect_batch_records(self, db: Session, push_type: str) -> list[HotlineRecord]:
        threshold_days = 1 if push_type == self.PUSH_DAILY else 7
        cutoff = datetime.utcnow() - timedelta(days=threshold_days)
        # Prefer recently screened, urgent or public-interest clues.
        records = list(
            db.scalars(
                select(HotlineRecord)
                .where(HotlineRecord.status == "已筛查")
                .order_by(HotlineRecord.id.desc())
                .limit(120)
            ).all()
        )
        filtered = [
            record
            for record in records
            if (
                record.warning_level in {"中", "高"}
                or record.public_interest_level == "公益"
                or (record.duplicate_count or 0) >= 3
                or (record.screened_at and record.screened_at >= cutoff)
            )
        ]
        return filtered[:30]

    def _build_batch_payload(self, db: Session, push_type: str, records: list[HotlineRecord]) -> dict:
        from huxin_platform.repositories.platform_repository import build_analysis_payload

        analysis_payload = build_analysis_payload(db)
        report = analysis_payload["special_report"]
        return {
            "push_type": push_type,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": report["summary_lines"],
            "metrics": {
                "high_warning_count": report["high_warning_count"],
                "public_interest_count": report["public_interest_count"],
                "high_frequency_count": report["high_frequency_count"],
                "performance_anomaly_count": report.get("performance_anomaly_count", 0),
            },
            "item_count": len(records),
            "items": [self._build_record_card(record) for record in records],
        }

    def _build_emergency_payload(self, records: list[HotlineRecord]) -> dict:
        return {
            "push_type": self.PUSH_EMERGENCY,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "item_count": len(records),
            "items": [self._build_record_card(record, urgent=True) for record in records],
        }

    def _build_record_card(self, record: HotlineRecord, urgent: bool = False) -> dict:
        return {
            "ticket_no": record.ticket_no,
            "title": record.title,
            "district": record.district or "",
            "location_text": record.location_text or "",
            "legal_domain": record.legal_domain or "",
            "domain_confidence": float(record.domain_confidence or 0.0),
            "public_interest_level": record.public_interest_level,
            "warning_level": record.warning_level or "无",
            "warning_summary": record.warning_reason_summary or "",
            "duplicate_level": record.duplicate_level or "无",
            "duplicate_count": record.duplicate_count or 1,
            "duration_days": record.duration_days or 0,
            "performance_anomaly_level": record.performance_anomaly_level or "无",
            "priority_level": record.priority_level or "低",
            "screening_summary": record.screening_summary or "",
            "complaint_excerpt": (record.complaint_text or "")[:240],
            "is_urgent": urgent or record.warning_level == "高",
        }

    def _serialize_source(self, config: SourceRuntimeConfig) -> dict:
        if config.mode == "http" and config.endpoint:
            status = "已就绪，可对接真实工单接口"
        elif config.mode == "http":
            status = "缺少真实接口地址，暂无法联调"
        elif config.mode == "demo":
            status = "演示拉取模式，可直接体验"
        else:
            status = "标准接入框架已预留"

        return {
            "source_system": config.source_system,
            "mode": config.mode,
            "endpoint": config.endpoint or "未配置",
            "auth_type": config.auth_type,
            "pull_strategy": config.pull_strategy,
            "status": status,
        }

    def _build_source_config(self, source_system: str) -> SourceRuntimeConfig:
        key = self._source_labels.get(source_system)
        if not key:
            raise ValueError("不支持的外部来源")

        base_url = getattr(settings, f"source_{key}_url")
        path = getattr(settings, f"source_{key}_path")
        mode = getattr(settings, f"source_{key}_mode") or settings.integration_mode or "demo"
        auth_type = getattr(settings, f"source_{key}_auth_type")
        token = getattr(settings, f"source_{key}_token")
        app_key = getattr(settings, f"source_{key}_app_key")
        app_secret = getattr(settings, f"source_{key}_app_secret")
        http_method = getattr(settings, f"source_{key}_http_method").upper()
        pull_strategy = getattr(settings, f"source_{key}_pull_strategy")
        timeout_seconds = getattr(settings, f"source_{key}_timeout_seconds") or settings.integration_timeout_seconds

        endpoint = self._compose_endpoint(base_url, path)
        normalized_mode = "demo" if mode == "reserved" else mode
        return SourceRuntimeConfig(
            source_system=source_system,
            mode=normalized_mode,
            endpoint=endpoint,
            auth_type=auth_type,
            token=token,
            app_key=app_key,
            app_secret=app_secret,
            http_method=http_method,
            pull_strategy=pull_strategy,
            timeout_seconds=timeout_seconds,
        )

    def _compose_endpoint(self, base_url: str, path: str) -> str:
        if not base_url:
            return path or ""
        if not path:
            return base_url
        return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))

    def _fetch_source_payload(self, config: SourceRuntimeConfig) -> dict:
        if config.mode == "http":
            return self._pull_http_source(config)
        if config.mode == "demo":
            return self._pull_demo_payload(config.source_system)
        raise ValueError("当前来源模式不支持拉取")

    def _pull_demo_payload(self, source_system: str) -> dict:
        demo_payloads = {
            "12345": {
                "external_id": "12345-DEMO",
                "ticket_no": "12345-DEMO-2026-01",
                "title": "工地欠薪示例工单",
                "complainant_name": "赵师傅",
                "complainant_phone": "13800001234",
                "district": "房山区",
                "location_text": "房山区长阳镇地铁站南侧安置房项目",
                "event_time": "2026-04-10 08:50",
                "complaint_text": "12345 转办：反映房山区长阳镇地铁站南侧安置房项目拖欠7名工人两个月工资共5.2万元。",
            },
            "街道综治": {
                "external_id": "STREET-DEMO",
                "ticket_no": "STREET-DEMO-2026-01",
                "title": "街道移交环境工单",
                "complainant_name": "周女士",
                "complainant_phone": "13800004567",
                "district": "房山区",
                "location_text": "房山区韩村河镇中心街北口",
                "event_time": "2026-04-10 10:15",
                "complaint_text": "街道综治移交：韩村河镇中心街北口长期垃圾堆放并伴随污水横流，居民持续投诉。",
            },
            "检察业务": {
                "external_id": "PROC-DEMO",
                "ticket_no": "PROC-DEMO-2026-01",
                "title": "业务移送行政监督工单",
                "complainant_name": "企业联系人",
                "complainant_phone": "13800007890",
                "district": "房山区",
                "location_text": "房山区阎村镇科技园",
                "event_time": "2026-04-10 14:30",
                "complaint_text": "检察业务移送：企业反映阎村镇科技园存在小过重罚、同案不同罚以及程序不规范问题。",
            },
        }

        payload = demo_payloads.get(source_system)
        if not payload:
            raise ValueError("不支持的外部来源")
        return {
            "external_id": payload["external_id"],
            "raw_payload": payload,
            "payload": payload,
            "sync_status": "已拉取待导入",
        }

    def _pull_http_source(self, config: SourceRuntimeConfig) -> dict:
        if not config.endpoint:
            raise ValueError(f"{config.source_system} 未配置真实接口地址")

        headers = self._build_auth_headers(config)
        with httpx.Client(timeout=config.timeout_seconds) as client:
            if config.http_method == "POST":
                response = client.post(config.endpoint, headers=headers, json={})
            else:
                response = client.get(config.endpoint, headers=headers)
            response.raise_for_status()

        raw_payload = self._extract_effective_payload(response)
        normalized_payload = self._normalize_payload(config.source_system, raw_payload)
        return {
            "external_id": normalized_payload["external_id"],
            "raw_payload": raw_payload,
            "payload": normalized_payload["record_payload"],
            "sync_status": "已拉取待导入",
        }

    def _build_auth_headers(self, config: SourceRuntimeConfig) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if config.auth_type == "bearer" and config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        elif config.auth_type == "token" and config.token:
            headers["X-Access-Token"] = config.token
        elif config.auth_type == "app_secret":
            if config.app_key:
                headers["X-App-Key"] = config.app_key
            if config.app_secret:
                headers["X-App-Secret"] = config.app_secret
        return headers

    def _extract_effective_payload(self, response: httpx.Response) -> dict:
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            raise ValueError("外部接口未返回 JSON 数据")

        body = response.json()
        if isinstance(body, list):
            if not body:
                raise ValueError("外部接口未返回有效数据")
            return body[0]
        if isinstance(body, dict):
            for key in ("data", "items", "records", "rows", "result"):
                value = body.get(key)
                if isinstance(value, list) and value:
                    return value[0]
                if isinstance(value, dict) and value:
                    return value
            return body
        raise ValueError("外部接口返回结构无法识别")

    def _normalize_payload(self, source_system: str, raw_payload: dict) -> dict:
        external_id = self._pick_first_value(
            raw_payload,
            ["external_id", "id", "ticket_id", "work_order_no", "serial_no", "case_no"],
        )
        title = self._pick_first_value(raw_payload, ["title", "subject", "name", "theme"])
        complaint_text = self._pick_first_value(
            raw_payload,
            ["complaint_text", "description", "content", "detail", "summary", "appeal", "problem"],
        )
        location_text = self._pick_first_value(
            raw_payload,
            ["location_text", "address", "address_name", "point_name", "place", "site"],
        )
        event_time = self._pick_first_value(
            raw_payload,
            ["event_time", "occurred_at", "report_time", "created_at", "submit_time", "accept_time"],
        )
        record_payload = {
            "ticket_no": str(external_id) if external_id is not None else f"{source_system}-{datetime.utcnow().timestamp()}",
            "source": source_system,
            "channel": "外部系统导入",
            "title": str(title or f"{source_system}导入工单"),
            "complainant_name": self._pick_first_value(raw_payload, ["complainant_name", "name", "person_name", "complainant"]),
            "complainant_phone": self._pick_first_value(raw_payload, ["phone", "mobile", "contact_phone", "phone_number", "tel"]),
            "district": self._pick_first_value(raw_payload, ["district", "area", "region"]) or "待核实",
            "location_text": str(location_text or ""),
            "event_time": str(event_time or ""),
            "complaint_text": str(complaint_text or "外部系统返回了工单，但缺少可直接展示的投诉内容。"),
        }
        return {
            "external_id": record_payload["ticket_no"],
            "record_payload": record_payload,
        }

    def _pick_first_value(self, payload: dict, keys: list[str]) -> str | float | int | None:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value
        return None

    def _build_summary(self, payload: dict) -> str:
        title = payload.get("title") or "导入工单"
        location = payload.get("location_text") or "待核实点位"
        return f"{title}，点位：{location}"

    def _upsert_sync_record(
        self,
        db: Session,
        config: SourceRuntimeConfig,
        raw_external_id: str | None,
        raw_payload: dict,
        normalized_payload: dict,
        normalized_summary: str,
        sync_status: str,
    ):
        payload = {
            "source_system": config.source_system,
            "mode": config.mode,
            "raw_external_id": raw_external_id,
            "sync_status": sync_status,
            "payload_json": raw_payload,
            "normalized_payload_json": normalized_payload,
            "normalized_summary": normalized_summary,
            "error_message": None,
            "last_synced_at": datetime.utcnow(),
        }
        existing_record = get_external_sync_record_by_raw_id(db, config.source_system, raw_external_id)
        if existing_record:
            return update_external_sync_record(db, existing_record, payload)
        return create_external_sync_record(db, payload)
