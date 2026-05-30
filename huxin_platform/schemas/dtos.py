from __future__ import annotations

from pydantic import BaseModel, Field


class ClueCreate(BaseModel):
    worker_name: str
    phone: str
    company: str
    source: str
    amount: float
    description: str


class ConsultationRequest(BaseModel):
    question: str
    clue_id: int | None = None
    use_llm: bool = False


class DocumentGenerateRequest(BaseModel):
    doc_type: str
    name: str
    phone: str
    id_card: str
    company: str
    amount: str
    join_date: str
    job_title: str
    evidence: str = ""
    clue_id: int | None = None
    consultation_id: int | None = None
    use_llm: bool = False


class ApplicationCreate(BaseModel):
    applicant_name: str
    phone: str
    company: str
    apply_type: str
    case_summary: str
    clue_id: int | None = None
    consultation_id: int | None = None
    document_id: int | None = None


class SyncPullRequest(BaseModel):
    source_system: str = Field(..., description="12345 / 街道综治 / 检察业务")


class IntegrationSourceItem(BaseModel):
    source_system: str
    mode: str
    endpoint: str
    auth_type: str
    pull_strategy: str
    status: str


class IntegrationPullResult(BaseModel):
    record_id: int
    source_system: str
    mode: str
    sync_status: str
    summary: str
    payload: dict
    external_id: str | None = None
    error_message: str | None = None
