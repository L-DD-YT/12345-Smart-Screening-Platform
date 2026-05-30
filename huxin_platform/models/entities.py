from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from huxin_platform.db.session import Base


class HotlineRecord(Base):
    __tablename__ = "hotline_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_no: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(50), default="12345")
    channel: Mapped[str] = mapped_column(String(50), default="市民投诉热线")
    title: Mapped[str] = mapped_column(String(200), default="12345投诉工单")
    complainant_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    complainant_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    complaint_text: Mapped[str] = mapped_column(Text)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="待筛查")
    has_location: Mapped[bool] = mapped_column(Boolean, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_group: Mapped[str | None] = mapped_column(String(120), nullable=True)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = mapped_column(String(50), default="待识别")
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    procuratorial_type: Mapped[str] = mapped_column(String(50), default="其他")
    is_procuratorial: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="低")
    priority_level: Mapped[str] = mapped_column(String(20), default="低")
    priority_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    public_interest_level: Mapped[str] = mapped_column(String(20), default="待复核")
    public_interest_score: Mapped[float] = mapped_column(Float, default=0.0)
    public_interest_reasons_json: Mapped[list] = mapped_column(JSON, default=list)
    public_interest_evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    legal_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    domain_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    domain_tags_json: Mapped[list] = mapped_column(JSON, default=list)
    domain_candidates_json: Mapped[list] = mapped_column(JSON, default=list)
    domain_conflict_flags_json: Mapped[list] = mapped_column(JSON, default=list)
    resolved_status: Mapped[str] = mapped_column(String(20), default="待核实")
    satisfaction_status: Mapped[str] = mapped_column(String(20), default="待核实")
    response_status: Mapped[str] = mapped_column(String(20), default="待核实")
    duplicate_level: Mapped[str] = mapped_column(String(20), default="无")
    duplicate_reasons_json: Mapped[list] = mapped_column(JSON, default=list)
    warning_level: Mapped[str] = mapped_column(String(20), default="无")
    warning_flags_json: Mapped[list] = mapped_column(JSON, default=list)
    warning_reason_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performance_anomaly_level: Mapped[str] = mapped_column(String(20), default="无")
    performance_anomaly_reasons_json: Mapped[list] = mapped_column(JSON, default=list)
    duration_days: Mapped[int] = mapped_column(Integer, default=0)
    matched_rules_json: Mapped[list] = mapped_column(JSON, default=list)
    structured_fields_json: Mapped[dict] = mapped_column(JSON, default=dict)
    screening_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(50), default="待标注")
    manual_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    handling_status: Mapped[str] = mapped_column(String(50), default="待研判")
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    screening_version: Mapped[str] = mapped_column(String(50), default="rules-v1")
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feature_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    screening_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ml_prediction_json: Mapped[dict] = mapped_column(JSON, default=dict)
    dl_prediction_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ensemble_prediction_json: Mapped[dict] = mapped_column(JSON, default=dict)
    semantic_keywords_json: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized_point_json: Mapped[dict] = mapped_column(JSON, default=dict)
    semantic_vector_json: Mapped[list] = mapped_column(JSON, default=list)
    point_cluster_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    point_cluster_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    aggressive_cluster_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sync_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    screened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExportRecord(Base):
    __tablename__ = "export_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    export_scope: Mapped[str] = mapped_column(String(100), default="全部台账")
    export_format: Mapped[str] = mapped_column(String(20), default="csv")
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    file_name: Mapped[str] = mapped_column(String(200))
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExternalSyncRecord(Base):
    __tablename__ = "external_sync_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_system: Mapped[str] = mapped_column(String(50))
    mode: Mapped[str] = mapped_column(String(50), default="demo")
    raw_external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(50), default="待同步")
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="fallback")
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    capability: Mapped[str] = mapped_column(String(50))
    prompt_preview: Mapped[str] = mapped_column(Text)
    response_preview: Mapped[str] = mapped_column(Text)
    call_status: Mapped[str] = mapped_column(String(30), default="ok")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ScreeningJobRecord(Base):
    __tablename__ = "screening_job_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_name: Mapped[str] = mapped_column(String(100), default="batch-screening")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    processed_records: Mapped[int] = mapped_column(Integer, default=0)
    high_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    procuratorial_count: Mapped[int] = mapped_column(Integer, default=0)
    batch_size: Mapped[int] = mapped_column(Integer, default=500)
    only_pending: Mapped[bool] = mapped_column(Boolean, default=True)
    record_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    screening_version: Mapped[str] = mapped_column(String(50), default="rules-v1")
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feature_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelArtifactRecord(Base):
    __tablename__ = "model_artifact_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    model_type: Mapped[str] = mapped_column(String(30), index=True)
    model_name: Mapped[str] = mapped_column(String(150))
    model_version: Mapped[str] = mapped_column(String(100), index=True)
    file_path: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    extra_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PushTaskRecord(Base):
    __tablename__ = "push_task_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    push_type: Mapped[str] = mapped_column(String(50), default="daily")
    trigger_mode: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    target_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
