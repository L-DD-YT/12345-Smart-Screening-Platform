from __future__ import annotations

import re

from sqlalchemy.orm import Session

from huxin_platform.repositories.platform_repository import (
    create_consultation,
    create_llm_log,
    get_clue_by_id,
)
from huxin_platform.services.legal_knowledge_service import LegalKnowledgeService
from huxin_platform.services.llm_service import LLMService


QA_RULES = [
    {
        "keywords": ("欠薪", "工资", "拖欠", "讨薪"),
        "answer": "如存在拖欠工资情形，建议先固定劳动关系和欠薪事实证据，再通过劳动监察、仲裁或诉讼依法维权。",
        "suggestion": "优先填写线索并生成文书，必要时同步申请支持起诉和法律援助。",
        "materials": ["身份证明", "劳动关系证明", "工资欠付证明", "聊天或催要记录"],
        "urgency": "高",
    },
    {
        "keywords": ("合同", "劳动合同", "没签合同"),
        "answer": "未签劳动合同不当然影响劳动关系认定，可通过工资流水、考勤、工牌、聊天记录等补强证明。",
        "suggestion": "建议先补齐劳动关系证明材料，再进入文书生成模块。",
        "materials": ["工资流水", "考勤记录", "工牌照片", "工作群聊天记录"],
        "urgency": "中",
    },
    {
        "keywords": ("仲裁", "起诉", "法院"),
        "answer": "劳动争议一般先仲裁后诉讼；符合法定条件的，可以申请检察机关支持起诉。",
        "suggestion": "可先在线提交案件情况，平台将辅助你生成申请材料。",
        "materials": ["仲裁材料", "证据目录", "身份证明", "欠薪证据"],
        "urgency": "中",
    },
    {
        "keywords": ("工伤", "受伤", "事故"),
        "answer": "若在工作中受伤，应尽快固定诊断材料和事故经过，并判断是否需要先走工伤认定程序。",
        "suggestion": "平台可先登记线索，但工伤赔偿事项建议同步申请法律援助。",
        "materials": ["病历", "诊断证明", "事故说明", "劳动关系证明"],
        "urgency": "高",
    },
]


def _fallback_answer(question: str) -> dict:
    text = question.strip()
    if not text:
        return {
            "answer": "请输入你的问题，例如“公司拖欠工资怎么办”。",
            "suggestion": "尽量写明欠薪、合同、仲裁等关键词。",
            "materials": [],
            "urgency": "提示",
            "provider": "fallback",
            "model_name": "fallback",
            "mode": "规则兜底",
        }

    for rule in QA_RULES:
        if any(keyword in text for keyword in rule["keywords"]):
            return {
                "answer": rule["answer"],
                "suggestion": rule["suggestion"],
                "materials": rule["materials"],
                "urgency": rule["urgency"],
                "provider": "fallback",
                "model_name": "fallback",
                "mode": "规则兜底",
            }

    return {
        "answer": "建议你先整理劳动关系、欠薪事实和沟通记录，再通过平台提交线索或申请服务。",
        "suggestion": "如果方便，请补充更具体的问题场景，以便平台给出更准确建议。",
        "materials": ["身份证明", "劳动关系证明", "工资支付或欠付记录"],
        "urgency": "中",
        "provider": "fallback",
        "model_name": "fallback",
        "mode": "规则兜底",
    }


class QAService:
    """Question answering service with optional LLM enhancement."""

    def __init__(self) -> None:
        self.llm_service = LLMService()
        self.knowledge_service = LegalKnowledgeService()

    def answer(self, db: Session, question: str, clue_id: int | None = None, use_llm: bool = False) -> dict:
        fallback = _fallback_answer(question)
        result = fallback
        effective_use_llm = use_llm or self.llm_service.is_ready()
        clue = get_clue_by_id(db, clue_id)
        category = self.knowledge_service.classify_question(question)
        evidence_profile = self.knowledge_service.analyze_evidence(
            text="\n".join(
                filter(
                    None,
                    [
                        question,
                        getattr(clue, "description", ""),
                        getattr(clue, "summary", ""),
                    ],
                )
            ),
            category=category,
        )
        knowledge_snippets = self.knowledge_service.retrieve(question=question, category=category)
        case_context = self._build_case_context(
            question=question,
            clue=clue,
            fallback=fallback,
            category=category,
            evidence_profile=evidence_profile,
        )

        if effective_use_llm:
            llm_result = self.llm_service.answer_question(
                question=question,
                case_context=case_context,
                fallback_context=fallback,
                category=category,
                knowledge_snippets=knowledge_snippets,
                evidence_profile=evidence_profile,
            )
            create_llm_log(
                db,
                {
                    "provider": llm_result.provider,
                    "model_name": llm_result.model_name,
                    "capability": "qa",
                    "prompt_preview": str(case_context)[:500],
                    "response_preview": (llm_result.content or llm_result.error_message or "")[:500],
                    "call_status": llm_result.status,
                    "error_message": llm_result.error_message,
                },
            )
            structured_result = self._build_llm_answer(
                payload=llm_result.metadata,
                fallback=fallback,
                category=category,
                knowledge_snippets=knowledge_snippets,
                evidence_profile=evidence_profile,
                llm_result=llm_result,
            )
            if structured_result:
                result = {
                    **structured_result,
                    "provider": llm_result.provider,
                    "model_name": llm_result.model_name,
                    "mode": llm_result.mode,
                    "usage": llm_result.usage or {},
                    "references": llm_result.references or {},
                    "request_id": llm_result.request_id,
                }
        else:
            result = {
                **self._build_fallback_professional_answer(
                    fallback=fallback,
                    category=category,
                    knowledge_snippets=knowledge_snippets,
                    evidence_profile=evidence_profile,
                ),
                "provider": fallback["provider"],
                "model_name": fallback["model_name"],
                "mode": fallback["mode"],
            }

        consultation = create_consultation(
            db,
            {
                "question": question,
                "answer": result["answer"],
                "suggestion": result["suggestion"],
                "urgency": result["urgency"],
                "materials_json": result["materials"],
                "provider": result["provider"],
                "model_name": result["model_name"],
                "mode": result["mode"],
            },
        )

        return {
            **result,
            "consultation_id": consultation.id,
        }

    def _build_case_context(self, question: str, clue, fallback: dict, category: str, evidence_profile: dict) -> dict:
        return {
            "question": question,
            "case_type": category,
            "worker_name": getattr(clue, "worker_name", ""),
            "company": getattr(clue, "company", ""),
            "source": getattr(clue, "source", ""),
            "amount": getattr(clue, "amount", ""),
            "status": getattr(clue, "status", ""),
            "description": getattr(clue, "description", ""),
            "summary": getattr(clue, "summary", ""),
            "fallback_materials": fallback["materials"],
            "existing_evidence": evidence_profile["existing_evidence"],
            "missing_evidence": evidence_profile["missing_evidence"],
        }

    def _build_llm_answer(
        self,
        payload: dict | None,
        fallback: dict,
        category: str,
        knowledge_snippets: list[dict],
        evidence_profile: dict,
        llm_result,
    ) -> dict | None:
        if not payload:
            text_fallback = (llm_result.content or "").strip()
            if text_fallback:
                return self._build_text_based_llm_answer(
                    answer_text=text_fallback,
                    fallback=fallback,
                    category=category,
                    knowledge_snippets=knowledge_snippets,
                    evidence_profile=evidence_profile,
                    references=llm_result.references or {},
                )
            return self._build_fallback_professional_answer(
                fallback=fallback,
                category=category,
                knowledge_snippets=knowledge_snippets,
                evidence_profile=evidence_profile,
            )

        action_plan = payload.get("action_plan") or []
        existing_evidence = payload.get("existing_evidence") or evidence_profile["existing_evidence"]
        missing_evidence = payload.get("missing_evidence") or evidence_profile["missing_evidence"]
        priority_evidence = payload.get("priority_evidence") or evidence_profile["priority_evidence"]
        legal_basis = payload.get("legal_basis") or [item["title"] for item in knowledge_snippets[:3]]
        if isinstance(action_plan, str):
            action_plan = [item.strip(" -\n") for item in action_plan.splitlines() if item.strip()]
        if isinstance(existing_evidence, str):
            existing_evidence = [item.strip(" -\n") for item in existing_evidence.splitlines() if item.strip()]
        if isinstance(missing_evidence, str):
            missing_evidence = [item.strip(" -\n") for item in missing_evidence.splitlines() if item.strip()]
        if isinstance(priority_evidence, str):
            priority_evidence = [item.strip(" -\n") for item in priority_evidence.splitlines() if item.strip()]
        if isinstance(legal_basis, str):
            legal_basis = [item.strip(" -\n") for item in legal_basis.splitlines() if item.strip()]
        case_assessment = str(payload.get("case_assessment") or "").strip()
        risk_notice = str(payload.get("risk_notice") or "").strip()
        case_type = str(payload.get("case_type") or category).strip()
        support_litigation = str(payload.get("support_litigation") or "可视情况申请").strip()
        legal_aid = str(payload.get("legal_aid") or "可视情况申请").strip()
        references = llm_result.references or {}
        reference_laws = references.get("laws") or []
        if reference_laws:
            legal_basis = (legal_basis[:4] if isinstance(legal_basis, list) else []) + [
                item for item in reference_laws if item not in legal_basis
            ]
        legal_basis = self._normalize_legal_basis_items(legal_basis, knowledge_snippets)

        professional_answer_parts = [
            f"案件判断：{case_type}",
            f"专业分析：{case_assessment or fallback['answer']}",
        ]
        if action_plan:
            professional_answer_parts.append(
                "维权路径：\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(action_plan[:3]))
            )
        if legal_basis:
            professional_answer_parts.append(
                "法律依据与办案要点：\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(legal_basis[:4]))
            )
        professional_answer_parts.append(f"风险提示：{risk_notice or '如事实和证据不足，部分主张仍需进一步补强。'}")

        suggestion = (
            f"支持起诉判断：{support_litigation}；法律援助判断：{legal_aid}。"
            f"{action_plan[0] if action_plan else fallback['suggestion']}"
        )

        urgency = fallback["urgency"]
        if any(keyword in case_type for keyword in ("拖欠", "工伤", "报酬")):
            urgency = "高"

        return {
            "answer": "\n\n".join(professional_answer_parts),
            "suggestion": suggestion,
            "materials": priority_evidence[:6] or fallback["materials"],
            "urgency": urgency,
            "case_type": case_type,
            "support_litigation": support_litigation,
            "legal_aid": legal_aid,
            "risk_notice": risk_notice or "如证据不足或程序选择不当，可能影响后续维权效果。",
            "existing_evidence": existing_evidence[:6],
            "missing_evidence": missing_evidence[:6],
            "priority_evidence": priority_evidence[:6],
            "legal_basis": legal_basis[:4],
        }

    def _build_text_based_llm_answer(
        self,
        answer_text: str,
        fallback: dict,
        category: str,
        knowledge_snippets: list[dict],
        evidence_profile: dict,
        references: dict,
    ) -> dict:
        normalized_answer = self._normalize_plain_answer(answer_text, fallback["answer"])
        legal_basis = [item["title"] for item in knowledge_snippets[:3]]
        legal_basis.extend(item for item in references.get("laws", []) if item not in legal_basis)
        legal_basis = self._normalize_legal_basis_items(legal_basis, knowledge_snippets)
        return {
            "answer": normalized_answer,
            "suggestion": fallback["suggestion"],
            "materials": evidence_profile["priority_evidence"][:6] or fallback["materials"],
            "urgency": fallback["urgency"],
            "case_type": category,
            "support_litigation": "可视情况申请",
            "legal_aid": "可视情况申请",
            "risk_notice": "请结合通义法睿返回内容和实际证据进一步核实案件事实。",
            "existing_evidence": evidence_profile["existing_evidence"][:6],
            "missing_evidence": evidence_profile["missing_evidence"][:6],
            "priority_evidence": evidence_profile["priority_evidence"][:6],
            "legal_basis": legal_basis[:4],
        }

    @staticmethod
    def _normalize_legal_basis_items(items: list, knowledge_snippets: list[dict]) -> list[str]:
        normalized: list[str] = []
        for item in items or []:
            text = str(item or "").strip()
            if not text:
                continue
            if text.startswith("{") and text.endswith("}"):
                continue
            if "lawId" in text and "lawItemId" in text:
                continue
            if text not in normalized:
                normalized.append(text)
        if normalized:
            return normalized
        return [item["title"] for item in knowledge_snippets[:3]]

    @staticmethod
    def _normalize_plain_answer(answer_text: str, fallback_answer: str) -> str:
        cleaned = re.sub(r"<referInfo>.*?</referInfo>", "", answer_text, flags=re.DOTALL).strip()
        cleaned = re.sub(r"</?[^>]+>", "", cleaned)
        cleaned = cleaned.replace("\\n", "\n") if cleaned.count("\\n") > cleaned.count("\n") else cleaned
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if not cleaned:
            return fallback_answer
        json_markers = ('"case_type"', '"case_assessment"', '"action_plan"', "{", "}")
        if sum(marker in cleaned for marker in json_markers) >= 3:
            return (
                f"案件判断：{fallback_answer}\n\n"
                "模型已返回原始结构化内容，但未能完全整理为展示格式。"
                "当前已自动回退为摘要展示，请结合下方材料与证据建议继续办理。"
            )
        return cleaned

    def _build_fallback_professional_answer(
        self,
        fallback: dict,
        category: str,
        knowledge_snippets: list[dict],
        evidence_profile: dict,
    ) -> dict:
        legal_basis = [item["title"] for item in knowledge_snippets[:3]]
        answer = [
            f"案件判断：{category}",
            f"专业分析：{fallback['answer']}",
            f"维权路径：\n1. {fallback['suggestion']}",
        ]
        if legal_basis:
            answer.append(
                "法律依据与办案要点：\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(legal_basis))
            )
        answer.append("风险提示：如事实和证据不足，部分主张仍需进一步补强。")
        return {
            "answer": "\n\n".join(answer),
            "suggestion": fallback["suggestion"],
            "materials": evidence_profile["priority_evidence"][:6] or fallback["materials"],
            "urgency": fallback["urgency"],
            "case_type": category,
            "support_litigation": "可视情况申请",
            "legal_aid": "可视情况申请",
            "risk_notice": "如证据不足或程序材料缺失，可能影响后续维权效果。",
            "existing_evidence": evidence_profile["existing_evidence"][:6],
            "missing_evidence": evidence_profile["missing_evidence"][:6],
            "priority_evidence": evidence_profile["priority_evidence"][:6],
            "legal_basis": legal_basis,
        }
