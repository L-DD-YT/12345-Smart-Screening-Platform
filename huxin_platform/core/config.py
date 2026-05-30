from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings with local defaults and future-ready adapters."""

    app_name: str = "12345市民投诉热线数据中涉检线索智能筛查平台"
    app_env: str = "development"
    database_url: str = f"sqlite:///{(BASE_DIR / 'huxin.db').as_posix()}"
    screening_batch_size: int = 500
    export_batch_size: int = 1000
    export_preview_rows: int = 20
    max_query_page_size: int = 100
    model_confidence_threshold: float = 0.42
    rule_weight: float = 0.25
    ml_weight: float = 0.45
    semantic_weight: float = 0.30
    ml_min_samples: int = 12
    artifacts_dir: str = str(BASE_DIR / "artifacts")
    exports_dir: str = str(BASE_DIR / "exports")
    ml_model_filename: str = "ml_classifier.joblib"
    ml_metadata_filename: str = "ml_classifier.meta.json"
    semantic_metadata_filename: str = "semantic_model.meta.json"
    semantic_model_enabled: bool = True
    semantic_model_name: str = "BAAI/bge-small-zh-v1.5"
    semantic_model_device: str = "auto"
    semantic_max_length: int = 256
    semantic_search_enabled: bool = True
    semantic_search_top_k: int = 80
    semantic_vector_precision: int = 6
    point_aggressive_mode_enabled: bool = True
    point_aggressive_similarity_threshold: float = 0.82
    point_token_similarity_threshold: float = 0.35
    point_cluster_preview_limit: int = 8

    llm_provider: str = "fallback"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_name: str = ""
    llm_timeout_seconds: int = 25
    farui_access_key_id: str = ""
    farui_access_key_secret: str = ""
    farui_workspace_id: str = ""
    farui_app_id: str = "farui"
    farui_assistant_id: str = ""
    farui_assistant_version: str = "1.0.0"
    farui_deep_think: bool = True
    farui_online_search: bool = True

    integration_mode: str = "demo"
    integration_timeout_seconds: int = 20
    push_target_endpoint: str = ""
    push_max_retry: int = 3
    amap_web_key: str = ""
    source_12345_url: str = ""
    source_12345_path: str = ""
    source_12345_mode: str = ""
    source_12345_auth_type: str = "none"
    source_12345_token: str = ""
    source_12345_app_key: str = ""
    source_12345_app_secret: str = ""
    source_12345_http_method: str = "GET"
    source_12345_pull_strategy: str = "manual"
    source_12345_timeout_seconds: int | None = None
    source_street_url: str = ""
    source_street_path: str = ""
    source_street_mode: str = ""
    source_street_auth_type: str = "none"
    source_street_token: str = ""
    source_street_app_key: str = ""
    source_street_app_secret: str = ""
    source_street_http_method: str = "GET"
    source_street_pull_strategy: str = "manual"
    source_street_timeout_seconds: int | None = None
    source_procuratorate_url: str = ""
    source_procuratorate_path: str = ""
    source_procuratorate_mode: str = ""
    source_procuratorate_auth_type: str = "none"
    source_procuratorate_token: str = ""
    source_procuratorate_app_key: str = ""
    source_procuratorate_app_secret: str = ""
    source_procuratorate_http_method: str = "GET"
    source_procuratorate_pull_strategy: str = "manual"
    source_procuratorate_timeout_seconds: int | None = None

    enable_demo_seed: bool = True

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def get_llm_status() -> dict[str, str]:
    """Expose runtime model status for the UI."""
    mode = "规则引擎优先"
    provider = "fallback" if settings.llm_provider == "fallback" else "farui"
    access_key_id = settings.farui_access_key_id or settings.llm_api_key
    workspace_id = settings.farui_workspace_id
    if provider == "farui" and access_key_id and settings.farui_access_key_secret and workspace_id:
        mode = "规则引擎 + 法睿辅助"
    return {
        "provider": provider,
        "model_name": settings.llm_model_name or "farui-legal-advice",
        "mode": mode,
    }


def get_local_model_paths() -> dict[str, str]:
    """Expose local artifact locations for ML and semantic models."""
    artifact_root = Path(settings.artifacts_dir)
    export_root = Path(settings.exports_dir)
    return {
        "artifacts_dir": str(artifact_root),
        "exports_dir": str(export_root),
        "ml_model_path": str(artifact_root / settings.ml_model_filename),
        "ml_metadata_path": str(artifact_root / settings.ml_metadata_filename),
        "semantic_metadata_path": str(artifact_root / settings.semantic_metadata_filename),
    }


def get_integration_status() -> dict[str, str]:
    """Expose integration adapter status for the UI."""
    mode = settings.integration_mode
    if mode == "http":
        status = "已启用真实工单接口"
    elif mode == "demo":
        status = "演示工单接入模式"
    else:
        status = "已预留标准接入层"
    return {
        "mode": mode,
        "status": status,
    }
