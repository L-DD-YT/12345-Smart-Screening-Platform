from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from huxin_platform.core.config import settings
from huxin_platform.db.session import Base, SessionLocal, engine
from huxin_platform.models import entities  # noqa: F401
from huxin_platform.repositories.platform_repository import seed_demo_data


def _ensure_legacy_columns(session: Session) -> None:
    """Backfill columns when an older SQLite demo database already exists."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if "hotline_records" in existing_tables:
        hotline_columns = {column["name"] for column in inspector.get_columns("hotline_records")}
        hotline_additions = {
            "model_version": "ALTER TABLE hotline_records ADD COLUMN model_version VARCHAR(100)",
            "feature_version": "ALTER TABLE hotline_records ADD COLUMN feature_version VARCHAR(100)",
            "screening_confidence": "ALTER TABLE hotline_records ADD COLUMN screening_confidence FLOAT DEFAULT 0",
            "priority_level": "ALTER TABLE hotline_records ADD COLUMN priority_level VARCHAR(20) DEFAULT '低'",
            "priority_reason": "ALTER TABLE hotline_records ADD COLUMN priority_reason VARCHAR(255)",
            "public_interest_level": "ALTER TABLE hotline_records ADD COLUMN public_interest_level VARCHAR(20) DEFAULT '待复核'",
            "public_interest_score": "ALTER TABLE hotline_records ADD COLUMN public_interest_score FLOAT DEFAULT 0",
            "public_interest_reasons_json": "ALTER TABLE hotline_records ADD COLUMN public_interest_reasons_json JSON",
            "public_interest_evidence_json": "ALTER TABLE hotline_records ADD COLUMN public_interest_evidence_json JSON",
            "legal_domain": "ALTER TABLE hotline_records ADD COLUMN legal_domain VARCHAR(100)",
            "domain_confidence": "ALTER TABLE hotline_records ADD COLUMN domain_confidence FLOAT DEFAULT 0",
            "domain_tags_json": "ALTER TABLE hotline_records ADD COLUMN domain_tags_json JSON",
            "domain_candidates_json": "ALTER TABLE hotline_records ADD COLUMN domain_candidates_json JSON",
            "domain_conflict_flags_json": "ALTER TABLE hotline_records ADD COLUMN domain_conflict_flags_json JSON",
            "resolved_status": "ALTER TABLE hotline_records ADD COLUMN resolved_status VARCHAR(20) DEFAULT '待核实'",
            "satisfaction_status": "ALTER TABLE hotline_records ADD COLUMN satisfaction_status VARCHAR(20) DEFAULT '待核实'",
            "response_status": "ALTER TABLE hotline_records ADD COLUMN response_status VARCHAR(20) DEFAULT '待核实'",
            "duplicate_level": "ALTER TABLE hotline_records ADD COLUMN duplicate_level VARCHAR(20) DEFAULT '无'",
            "duplicate_reasons_json": "ALTER TABLE hotline_records ADD COLUMN duplicate_reasons_json JSON",
            "warning_level": "ALTER TABLE hotline_records ADD COLUMN warning_level VARCHAR(20) DEFAULT '无'",
            "warning_flags_json": "ALTER TABLE hotline_records ADD COLUMN warning_flags_json JSON",
            "warning_reason_summary": "ALTER TABLE hotline_records ADD COLUMN warning_reason_summary VARCHAR(255)",
            "performance_anomaly_level": "ALTER TABLE hotline_records ADD COLUMN performance_anomaly_level VARCHAR(20) DEFAULT '无'",
            "performance_anomaly_reasons_json": "ALTER TABLE hotline_records ADD COLUMN performance_anomaly_reasons_json JSON",
            "duration_days": "ALTER TABLE hotline_records ADD COLUMN duration_days INTEGER DEFAULT 0",
            "ml_prediction_json": "ALTER TABLE hotline_records ADD COLUMN ml_prediction_json JSON",
            "dl_prediction_json": "ALTER TABLE hotline_records ADD COLUMN dl_prediction_json JSON",
            "ensemble_prediction_json": "ALTER TABLE hotline_records ADD COLUMN ensemble_prediction_json JSON",
            "semantic_keywords_json": "ALTER TABLE hotline_records ADD COLUMN semantic_keywords_json JSON",
            "normalized_point_json": "ALTER TABLE hotline_records ADD COLUMN normalized_point_json JSON",
            "semantic_vector_json": "ALTER TABLE hotline_records ADD COLUMN semantic_vector_json JSON",
            "point_cluster_id": "ALTER TABLE hotline_records ADD COLUMN point_cluster_id VARCHAR(100)",
            "point_cluster_label": "ALTER TABLE hotline_records ADD COLUMN point_cluster_label VARCHAR(200)",
            "aggressive_cluster_json": "ALTER TABLE hotline_records ADD COLUMN aggressive_cluster_json JSON",
            "first_seen_at": "ALTER TABLE hotline_records ADD COLUMN first_seen_at DATETIME",
            "last_seen_at": "ALTER TABLE hotline_records ADD COLUMN last_seen_at DATETIME",
        }
        for column_name, ddl in hotline_additions.items():
            if column_name not in hotline_columns:
                session.execute(text(ddl))

    if "external_sync_records" not in existing_tables:
        return

    sync_columns = {column["name"] for column in inspector.get_columns("external_sync_records")}
    if "normalized_payload_json" not in sync_columns:
        session.execute(text("ALTER TABLE external_sync_records ADD COLUMN normalized_payload_json JSON"))
    if "linked_record_id" not in sync_columns:
        session.execute(text("ALTER TABLE external_sync_records ADD COLUMN linked_record_id INTEGER"))
    if "last_synced_at" not in sync_columns:
        session.execute(text("ALTER TABLE external_sync_records ADD COLUMN last_synced_at DATETIME"))


def init_database() -> None:
    """Create ORM tables and seed local data."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        _ensure_legacy_columns(session)
        session.commit()
        if settings.enable_demo_seed:
            seed_demo_data(session)
