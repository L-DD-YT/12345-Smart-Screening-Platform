from __future__ import annotations

from datetime import datetime
import re

from sqlalchemy.orm import Session

from huxin_platform.repositories.platform_repository import (
    create_document,
    create_llm_log,
    get_clue_by_id,
    get_consultation_by_id,
)
from huxin_platform.services.llm_service import LLMService


DOC_TEMPLATES = {
    "complaint": """民事起诉状

原告：{name}
联系电话：{phone}
身份证号：{id_card}
用工单位：{company}

诉讼请求：
1. 请求依法判令被告支付拖欠工资人民币 {amount} 元；
2. 请求依法判令被告承担相应责任。

事实与理由：
原告于 {join_date} 起在 {company} 工作，从事 {job_title} 岗位。工作期间，被告拖欠原告工资 {amount} 元，经催要未果，现依法提起诉讼，请予支持。

此致
人民法院

具状人：{name}
日期：{today}
""",
    "support": """支持起诉申请书

申请人：{name}
联系电话：{phone}
身份证号：{id_card}

申请事项：
请求依法对申请人与 {company} 之间因拖欠劳动报酬引发的纠纷提供支持起诉帮助。

事实与理由：
申请人于 {join_date} 在 {company} 工作，从事 {job_title} 岗位。目前该单位拖欠工资 {amount} 元，申请人维权能力有限，现申请支持起诉。

主要证据：
{evidence_text}

申请人：{name}
日期：{today}
""",
    "aid": """法律援助申请信息表

申请人：{name}
联系电话：{phone}
身份证号：{id_card}
单位名称：{company}
申请事项：劳动报酬追索
诉求金额：{amount} 元

案件概述：
申请人于 {join_date} 入职 {company}，从事 {job_title} 岗位，现存在工资拖欠问题，特申请法律援助。

拟提交证据：
{evidence_text}

填报日期：{today}
""",
}


class DocumentService:
    """Document drafting with template fallback and optional LLM enhancement."""

    def __init__(self) -> None:
        self.llm_service = LLMService()

    def generate(
        self,
        db: Session,
        payload: dict,
        clue_id: int | None = None,
        consultation_id: int | None = None,
        use_llm: bool = False,
    ) -> dict:
        evidence_lines = [line.strip() for line in payload["evidence"].splitlines() if line.strip()]
        evidence_text = (
            "\n".join(f"{index + 1}. {line}" for index, line in enumerate(evidence_lines))
            or "1. 身份证明\n2. 劳动关系证明\n3. 工资欠付证明"
        )
        clue = get_clue_by_id(db, clue_id)
        consultation = get_consultation_by_id(db, consultation_id)
        doc_title = self._document_title(payload["doc_type"])
        case_info = {
            **payload,
            "evidence_text": evidence_text,
            "doc_title": doc_title,
            "linked_clue": {
                "worker_name": getattr(clue, "worker_name", ""),
                "company": getattr(clue, "company", ""),
                "source": getattr(clue, "source", ""),
                "amount": getattr(clue, "amount", ""),
                "description": getattr(clue, "description", ""),
                "summary": getattr(clue, "summary", ""),
            },
            "linked_consultation": {
                "question": getattr(consultation, "question", ""),
                "answer": getattr(consultation, "answer", ""),
                "suggestion": getattr(consultation, "suggestion", ""),
            },
        }

        template_content = DOC_TEMPLATES[payload["doc_type"]].format(
            name=payload["name"],
            phone=payload["phone"],
            id_card=payload["id_card"],
            company=payload["company"],
            amount=payload["amount"],
            join_date=payload["join_date"],
            job_title=payload["job_title"],
            evidence_text=evidence_text,
            today=datetime.now().strftime("%Y年%m月%d日"),
        )

        provider = "template"
        model_name = "template"
        mode = "模板生成"
        content = template_content
        effective_use_llm = use_llm or self.llm_service.is_ready()

        if effective_use_llm:
            llm_result = self.llm_service.draft_document(
                payload["doc_type"],
                case_info=case_info,
                template_content=template_content,
            )
            create_llm_log(
                db,
                {
                    "provider": llm_result.provider,
                    "model_name": llm_result.model_name,
                    "capability": "document",
                    "prompt_preview": str(case_info)[:500],
                    "response_preview": (llm_result.content or llm_result.error_message or "")[:500],
                    "call_status": llm_result.status,
                    "error_message": llm_result.error_message,
                },
            )
            normalized_content = self._normalize_document_content(
                doc_type=payload["doc_type"],
                content=llm_result.content,
                references=llm_result.references or {},
            )
            if normalized_content and self._is_valid_document(payload["doc_type"], normalized_content):
                provider = llm_result.provider
                model_name = llm_result.model_name
                mode = "专业润色"
                content = normalized_content

        document = create_document(
            db,
            {
                "doc_type": payload["doc_type"],
                "name": payload["name"],
                "phone": payload["phone"],
                "id_card": payload["id_card"],
                "company": payload["company"],
                "amount": payload["amount"],
                "join_date": payload["join_date"],
                "job_title": payload["job_title"],
                "evidence_text": evidence_text,
                "content": content,
                "provider": provider,
                "mode": mode,
            },
        )

        return {
            "title": doc_title,
            "content": content,
            "provider": provider,
            "model_name": model_name,
            "mode": mode,
            "document_id": document.id,
        }

    @staticmethod
    def _document_title(doc_type: str) -> str:
        title_map = {
            "complaint": "民事起诉状",
            "support": "支持起诉申请书",
            "aid": "法律援助申请信息表",
        }
        return title_map.get(doc_type, "法律文书")

    def _is_valid_document(self, doc_type: str, content: str) -> bool:
        required_sections = {
            "complaint": ["民事起诉状", "诉讼请求", "事实与理由"],
            "support": ["支持起诉申请书", "申请事项", "事实与理由"],
            "aid": ["法律援助申请信息表", "申请事项", "案件概述"],
        }
        expected = required_sections.get(doc_type, [])
        return all(section in content for section in expected)

    def _normalize_document_content(self, doc_type: str, content: str, references: dict) -> str:
        cleaned = (content or "").strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"<referInfo>.*?</referInfo>", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"[\(（]?\{[^{}]*(lawId|lawItemId|lawSourceContent|timeliness)[^{}]*\}[\)）]?", "", cleaned)
        cleaned = re.sub(r"</?[^>]+>", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

        legal_basis_lines = self._build_legal_basis_lines(references)
        if legal_basis_lines and "法律依据" not in cleaned:
            legal_basis_block = "法律依据：\n" + "\n".join(
                f"{index + 1}. {item}" for index, item in enumerate(legal_basis_lines[:3])
            )
            cleaned = self._insert_legal_basis_block(doc_type, cleaned, legal_basis_block)
        return cleaned

    @staticmethod
    def _build_legal_basis_lines(references: dict) -> list[str]:
        lines: list[str] = []
        for item in references.get("laws", []) if references else []:
            text = str(item or "").strip()
            if not text:
                continue
            if text not in lines:
                lines.append(text)
        return lines

    @staticmethod
    def _insert_legal_basis_block(doc_type: str, content: str, legal_basis_block: str) -> str:
        anchor_map = {
            "complaint": "\n此致",
            "support": "\n申请人：",
            "aid": "\n填报日期：",
        }
        anchor = anchor_map.get(doc_type, "")
        if anchor and anchor in content:
            return content.replace(anchor, f"\n{legal_basis_block}\n{anchor}", 1)
        return f"{content}\n\n{legal_basis_block}"
