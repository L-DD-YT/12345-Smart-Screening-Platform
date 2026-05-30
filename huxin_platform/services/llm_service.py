from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import httpx

from huxin_platform.core.config import settings


@dataclass
class LLMResult:
    content: str
    provider: str
    model_name: str
    mode: str
    status: str = "ok"
    error_message: str | None = None
    metadata: dict | None = None
    usage: dict | None = None
    references: dict | None = None
    request_id: str | None = None
    raw_payload: dict | None = None


class LLMService:
    """Farui-aware adapter with fallback-first behavior."""

    FARUI_HOST = "farui.cn-beijing.aliyuncs.com"
    FARUI_ACTION = "RunLegalAdviceConsultation"
    FARUI_VERSION = "2024-06-28"

    def __init__(self) -> None:
        configured_provider = (settings.llm_provider or "fallback").strip().lower()
        self.provider = "fallback" if configured_provider == "fallback" else "farui"
        self.base_url = (settings.llm_base_url or "").rstrip("/")
        self.model_name = settings.llm_model_name or "farui-legal-advice"
        self.access_key_id = settings.farui_access_key_id or settings.llm_api_key or ""
        self.access_key_secret = settings.farui_access_key_secret or ""
        self.workspace_id = settings.farui_workspace_id or self._extract_workspace_id(self.base_url)
        self.app_id = settings.farui_app_id or "farui"
        self.assistant_id = settings.farui_assistant_id or ""
        self.assistant_version = settings.farui_assistant_version or "1.0.0"
        self.deep_think_default = settings.farui_deep_think
        self.online_search_default = settings.farui_online_search

    def is_ready(self) -> bool:
        return self.provider == "farui" and bool(
            self.access_key_id and self.access_key_secret and self.workspace_id
        )

    def answer_question(
        self,
        question: str,
        case_context: dict,
        fallback_context: dict,
        category: str,
        knowledge_snippets: list[dict],
        evidence_profile: dict,
    ) -> LLMResult:
        category_prompt = self._qa_category_prompt(category)
        system_prompt = (
            "你是12345涉检智能筛查平台的专业涉检线索法律助手，服务对象主要是涉检线索筛查与复核场景。"
            "你的任务不是泛泛解释法律常识，而是结合案件事实、证据状况、平台知识库片段，输出专业、克制、可执行的维权指引。"
            f"当前咨询分类：{category}。{category_prompt}"
            "请重点围绕拖欠劳动报酬、劳动关系认定、证据准备、支持起诉、法律援助、仲裁诉讼路径进行分析。"
            "不要编造不存在的事实，不要引用虚假的法条条号；如事实不足，应明确说明仍需补充核实。"
            "不要输出 referInfo、XML 标签、Markdown 代码块或任何额外包裹标记。"
            "请只返回一个 JSON 对象，不要输出 Markdown，不要添加额外说明。"
            "JSON 字段必须包含：case_type, case_assessment, action_plan, existing_evidence, missing_evidence, priority_evidence, legal_basis, support_litigation, legal_aid, risk_notice。"
        )
        user_prompt = {
            "question": question,
            "case_context": case_context,
            "fallback_context": fallback_context,
            "evidence_profile": evidence_profile,
            "knowledge_snippets": knowledge_snippets,
            "output_schema": [
                "case_type：案件类型简短概括",
                "case_assessment：2-4句专业判断",
                "action_plan：3条以内分步维权路径",
                "existing_evidence：列出已识别的现有证据",
                "missing_evidence：列出缺失但建议补充的证据",
                "priority_evidence：列出最优先补强的 2-4 项证据",
                "legal_basis：列出 2-4 条可供平台展示的法律依据或办案规则要点，避免编造法条条号",
                "support_litigation：建议申请/可视情况申请/暂不建议申请 三选一，并体现理由",
                "legal_aid：建议申请/可视情况申请/暂不建议申请 三选一，并体现理由",
                "risk_notice：1-2句风险提示",
            ],
        }
        return self._chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            capability="qa",
            temperature=0.2,
            expect_json=True,
        )

    def summarize_clue(self, raw_text: str) -> LLMResult:
        prompt = {
            "task": "请将以下农民工欠薪线索摘要为一句简洁中文，保留主体、单位、核心争议和金额要点。",
            "content": raw_text,
        }
        return self._chat_completion(
            system_prompt="你是欠薪线索摘要助手，请输出一句简洁、准确的中文摘要。",
            user_prompt=prompt,
            capability="summarize",
            temperature=0.2,
        )

    def draft_document(self, doc_type: str, case_info: dict, template_content: str) -> LLMResult:
        doc_prompt = self._document_prompt(doc_type)
        system_prompt = (
            "你是劳动争议法律文书助手，请对平台生成的文书初稿进行专业润色。"
            "必须保持事实一致，不得虚构新事实、金额、证据、日期或法律程序。"
            "语气要正式、克制、法律化，适合法律文书预览。"
            f"{doc_prompt}"
            "如果引用法律依据，请使用“《法律名称》第X条（时效性）”这类正式中文格式表达。"
            "严禁输出 referInfo、JSON、字典、数组、XML 标签或法条引用原始对象。"
            "输出必须保持固定文书结构，不要改写为答复意见、说明文字或列表总结。"
            "优先优化“请求事项”“事实与理由”“证据指向”的表达，让文书更专业但不过度冗长。"
            "请直接返回最终文书正文，不要添加解释。"
        )
        user_prompt = {
            "doc_type": doc_type,
            "case_info": case_info,
            "template_content": template_content,
            "instruction": "请在不改变核心事实的前提下，输出一版更专业、规范、适合平台展示的正式中文文书。",
        }
        return self._chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            capability="document",
            temperature=0.1,
        )

    def _chat_completion(
        self,
        system_prompt: str,
        user_prompt: str | dict | list,
        capability: str,
        temperature: float,
        expect_json: bool = False,
    ) -> LLMResult:
        if not self.is_ready():
            return LLMResult(
                content="",
                provider="fallback",
                model_name="fallback",
                mode="规则兜底",
                status="skipped",
                error_message="模型未配置，已使用本地兜底逻辑。",
            )

        try:
            return self._farui_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                capability=capability,
                expect_json=expect_json,
            )
        except Exception as exc:  # noqa: BLE001
            return LLMResult(
                content="",
                provider="farui" if self.provider == "farui" else "fallback",
                model_name=self.model_name or "fallback",
                mode="规则兜底",
                status="error",
                error_message=str(exc),
            )

    def _farui_completion(
        self,
        system_prompt: str,
        user_prompt: str | dict | list,
        capability: str,
        expect_json: bool,
    ) -> LLMResult:
        host = self.FARUI_HOST
        url = f"https://{host}/{self.workspace_id}/farui/legalAdvice/consult"
        body = {
            "appId": self.app_id,
            "stream": True,
            "workspaceId": self.workspace_id,
            "thread": {
                "messages": [
                    {
                        "role": "user",
                        "content": self._build_farui_message(system_prompt, user_prompt, capability, expect_json),
                    }
                ]
            },
            "extra": self._build_farui_extra(capability),
        }
        if self.assistant_id:
            body["assistant"] = {
                "id": self.assistant_id,
                "metaData": self._build_assistant_metadata(capability, expect_json),
                "type": "legal_advice_consult",
                "version": self.assistant_version,
            }
        body_text = json.dumps(body, ensure_ascii=False)

        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        headers = {
            "host": host,
            "Content-Type": "application/json",
            "x-acs-action": self.FARUI_ACTION,
            "x-acs-version": self.FARUI_VERSION,
            "x-acs-date": timestamp,
        }
        headers["Authorization"] = self._ali_sign(url=url, method="POST", headers=headers, body_text=body_text)

        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            with client.stream("POST", url, headers=headers, content=body_text.encode("utf-8")) as response:
                response.raise_for_status()
                stream_result = self._consume_farui_stream(response)
                content = stream_result["content"]
        if not content.strip():
            raise ValueError("通义法睿返回为空，未生成可用内容。")
        content = self._sanitize_farui_content(content)
        parsed_metadata = self._extract_json_object(content) if expect_json else None

        return LLMResult(
            content=content,
            provider="farui",
            model_name=self.model_name,
            mode="模型增强",
            metadata=parsed_metadata,
            usage=stream_result["usage"],
            references=stream_result["references"],
            request_id=stream_result["request_id"],
            raw_payload=stream_result["raw_payload"],
            status="ok" if stream_result["success"] is not False else "error",
            error_message=stream_result["error_message"],
        )

    def _build_farui_message(
        self,
        system_prompt: str,
        user_prompt: str | dict | list,
        capability: str,
        expect_json: bool,
    ) -> str:
        serialized_user_prompt = self._serialize_content(user_prompt)
        instructions = [
            "你正在处理来自12345涉检智能筛查平台的业务请求。",
            f"当前任务类型：{capability}。",
            system_prompt.strip(),
            "以下是用户输入与结构化上下文，请严格基于给定事实回答。",
            serialized_user_prompt,
        ]
        if expect_json:
            instructions.append("请确保最终输出是一个合法 JSON 对象，不要输出代码块标记。")
        else:
            instructions.append("请直接输出最终结果，不要添加额外说明。")
        return "\n\n".join(part for part in instructions if part)

    def _build_assistant_metadata(self, capability: str, expect_json: bool) -> dict[str, str]:
        metadata = {
            "capability": capability,
            "responseFormat": "json" if expect_json else "text",
        }
        if capability == "document":
            metadata["scene"] = "legal_document_generation"
        elif capability == "summarize":
            metadata["scene"] = "clue_summary"
        else:
            metadata["scene"] = "legal_advice_consult"
        return metadata

    def _build_farui_extra(self, capability: str) -> dict:
        if capability in {"summarize", "document"}:
            return {"deepThink": False, "onlineSearch": False}
        return {
            "deepThink": self.deep_think_default,
            "onlineSearch": self.online_search_default,
        }

    def _consume_farui_stream(self, response: httpx.Response) -> dict:
        final_text = ""
        latest_markdown = ""
        last_payload: dict | None = None
        usage: dict | None = None
        request_id: str | None = None
        success: bool | None = None
        error_message: str | None = None
        references = {
            "laws": [],
            "cases": [],
            "searches": [],
        }

        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            last_payload = payload
            request_id = payload.get("RequestId") or request_id
            usage = payload.get("Usage") or usage
            success = payload.get("Success") if payload.get("Success") is not None else success
            error_message = payload.get("Message") or error_message

            markdown = str(payload.get("ResponseMarkdown") or "").strip()
            if markdown:
                latest_markdown = self._merge_stream_text(latest_markdown, markdown)

            text_content, extracted_references = self._extract_text_and_references_from_contents(payload.get("contents"))
            if text_content:
                final_text = self._merge_stream_text(final_text, text_content)
            self._merge_reference_bucket(references, extracted_references)

        return {
            "content": (latest_markdown or final_text).strip(),
            "usage": usage,
            "request_id": request_id,
            "references": references,
            "success": success,
            "error_message": error_message,
            "raw_payload": last_payload,
        }

    def _extract_text_and_references_from_contents(self, contents: str | list | None) -> tuple[str, dict]:
        if not contents:
            return "", {"laws": [], "cases": [], "searches": []}
        parsed_contents = contents
        if isinstance(contents, str):
            try:
                parsed_contents = json.loads(contents)
            except json.JSONDecodeError:
                return contents.strip(), {"laws": [], "cases": [], "searches": []}

        if not isinstance(parsed_contents, list):
            return "", {"laws": [], "cases": [], "searches": []}

        result = ""
        references = {
            "laws": [],
            "cases": [],
            "searches": [],
        }
        for item in parsed_contents:
            if not isinstance(item, dict):
                continue
            if item.get("contentType") == "text":
                result = self._merge_stream_text(result, str(item.get("content") or "").strip())
            if "lawList" in item:
                references["laws"].extend(self._normalize_reference_items(item.get("lawList")))
            if "caseList" in item:
                references["cases"].extend(self._normalize_reference_items(item.get("caseList")))
            if "searchList" in item:
                references["searches"].extend(self._normalize_reference_items(item.get("searchList")))
        return result.strip(), references

    def _serialize_content(self, content: str | dict | list | None) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, dict):
            return self._serialize_dict_content(content)
        if isinstance(content, list):
            blocks = [self._serialize_content(item) for item in content]
            return "\n\n".join(block for block in blocks if block.strip())
        return str(content).strip()

    def _serialize_dict_content(self, payload: dict) -> str:
        blocks: list[str] = []
        for key, value in payload.items():
            title = str(key).replace("_", " ").strip()
            if isinstance(value, list) and value and all(isinstance(item, dict) and "type" in item for item in value):
                blocks.append(self._serialize_multimodal_blocks(title, value))
                continue
            if isinstance(value, (dict, list)):
                body = json.dumps(value, ensure_ascii=False, indent=2)
            else:
                body = str(value)
            blocks.append(f"{title}:\n{body}")
        return "\n\n".join(block for block in blocks if block.strip())

    def _serialize_multimodal_blocks(self, title: str, blocks: list[dict]) -> str:
        lines = [f"{title}:"]
        for index, block in enumerate(blocks, start=1):
            block_type = str(block.get("type") or "unknown").strip()
            if block_type == "text":
                lines.append(f"{index}. [text] {str(block.get('text') or '').strip()}")
            elif block_type in {"image", "image_url"}:
                image_value = block.get("image_url") or block.get("url") or ""
                caption = str(block.get("caption") or "").strip()
                lines.append(f"{index}. [image] {image_value} {caption}".strip())
            elif block_type == "file":
                file_name = str(block.get("file_name") or block.get("name") or "unnamed").strip()
                summary = str(block.get("summary") or block.get("ocr_text") or block.get("text") or "").strip()
                lines.append(f"{index}. [file] {file_name} {summary}".strip())
            else:
                lines.append(f"{index}. [{block_type}] {json.dumps(block, ensure_ascii=False)}")
        return "\n".join(lines)

    @staticmethod
    def _normalize_reference_items(items: list | None) -> list[str]:
        if not items:
            return []
        normalized: list[str] = []
        for item in items:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = LLMService._format_reference_dict(item)
            else:
                text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    @staticmethod
    def _merge_reference_bucket(target: dict, source: dict) -> None:
        for key in ("laws", "cases", "searches"):
            for item in source.get(key, []):
                if item not in target[key]:
                    target[key].append(item)

    @staticmethod
    def _format_reference_dict(item: dict) -> str:
        law_name = str(item.get("lawName") or "").strip()
        law_item_name = str(item.get("lawItemName") or "").strip()
        timeliness = str(item.get("timeliness") or "").strip()
        source_content = str(item.get("lawSourceContent") or "").strip()

        parts: list[str] = []
        if law_name:
            parts.append(f"《{law_name}》")
        if law_item_name:
            parts.append(law_item_name)
        text = "".join(parts).strip()
        if timeliness:
            text = f"{text}（{timeliness}）" if text else timeliness
        if not text:
            title = str(item.get("title") or item.get("name") or "").strip()
            if title:
                text = title
        if source_content:
            snippet = re.sub(r"\s+", " ", source_content).strip()
            if len(snippet) > 90:
                snippet = f"{snippet[:90]}..."
            if text:
                text = f"{text}：{snippet}"
            else:
                text = snippet
        if text:
            return text
        return ""

    @staticmethod
    def _merge_stream_text(current: str, incoming: str) -> str:
        incoming = incoming.strip()
        if not incoming:
            return current
        if not current:
            return incoming
        if incoming.startswith(current):
            return incoming
        if current.endswith(incoming):
            return current
        max_overlap = min(len(current), len(incoming))
        for size in range(max_overlap, 0, -1):
            if current.endswith(incoming[:size]):
                return f"{current}{incoming[size:]}"
            if incoming.endswith(current[:size]):
                return incoming
        return f"{current}{incoming}"

    @staticmethod
    def _sanitize_farui_content(content: str) -> str:
        if not content:
            return ""
        cleaned = content.strip()
        cleaned = re.sub(r"<referInfo>.*?</referInfo>", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"</?[^>]+>", "", cleaned)
        cleaned = cleaned.replace("\ufeff", "")
        cleaned = cleaned.replace("\\n", "\n") if cleaned.count("\\n") > cleaned.count("\n") else cleaned
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _extract_candidate_json_objects(content: str) -> list[str]:
        candidates: list[str] = []
        start_index: int | None = None
        depth = 0
        in_string = False
        escape = False

        for index, char in enumerate(content):
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue
            if char == "{":
                if depth == 0:
                    start_index = index
                depth += 1
            elif char == "}":
                if depth == 0:
                    continue
                depth -= 1
                if depth == 0 and start_index is not None:
                    candidates.append(content[start_index : index + 1])
                    start_index = None
        return candidates

    def _ali_sign(self, url: str, method: str, headers: dict, body_text: str) -> str:
        url_object = urlparse(url)
        canonical_uri = url_object.path or "/"
        signed_header_names = sorted(
            key.lower()
            for key in headers
            if key.lower().startswith("x-acs-") or key.lower() in {"host", "content-type"}
        )
        headers_lower = {key.lower(): value for key, value in headers.items()}
        canonical_headers = "".join(
            f"{header}:{str(headers_lower[header]).strip()}\n" for header in signed_header_names
        )
        signed_headers = ";".join(signed_header_names)
        hashed_payload = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
        canonical_request = "\n".join(
            [method.upper(), canonical_uri, "", canonical_headers, signed_headers, hashed_payload]
        )
        hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"ACS3-HMAC-SHA256\n{hashed_request}"
        signature = hmac.new(
            self.access_key_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return (
            "ACS3-HMAC-SHA256 "
            f"Credential={self.access_key_id},SignedHeaders={signed_headers},Signature={signature}"
        )

    @staticmethod
    def _extract_workspace_id(base_url: str) -> str:
        if not base_url:
            return ""
        parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
        path_parts = [part for part in parsed.path.split("/") if part]
        if path_parts:
            return path_parts[0]
        return ""

    @staticmethod
    def _extract_json_object(content: str) -> dict | None:
        if not content:
            return None
        stripped = LLMService._sanitize_farui_content(content)
        candidates = [stripped]
        fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if fenced_match:
            candidates.insert(0, fenced_match.group(1))
        candidates = LLMService._extract_candidate_json_objects(stripped) + candidates

        for candidate in candidates:
            try:
                value = json.loads(candidate)
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def _qa_category_prompt(category: str) -> str:
        prompt_map = {
            "欠薪追索": "请重点分析欠薪事实、金额确定、追索路径和程序顺序。",
            "未签劳动合同": "请重点分析未签合同情况下的劳动关系证明思路和双倍工资等相关风险，但避免编造具体结论。",
            "劳动关系认定": "请重点分析如何证明管理从属性、报酬支付关系和工作事实。",
            "仲裁诉讼": "请重点分析仲裁前置、诉讼衔接以及程序材料准备。",
            "工伤赔偿": "请重点分析工伤认定、诊疗材料和赔偿请求衔接。",
            "支持起诉": "请重点分析是否符合支持起诉的适用场景与必要性。",
            "法律援助": "请重点分析是否符合申请法律援助的常见条件和所需材料。",
        }
        return prompt_map.get(category, "请围绕劳动权益保护输出专业、克制、可执行的指引。")

    @staticmethod
    def _document_prompt(doc_type: str) -> str:
        prompt_map = {
            "complaint": (
                "请确保文书严格包含“民事起诉状”标题、当事人信息、诉讼请求、事实与理由、落款五个部分，"
                "保持起诉状语体，不得写成咨询意见。"
            ),
            "support": (
                "请确保文书严格包含“支持起诉申请书”标题、申请人信息、申请事项、事实与理由、主要证据、落款六个部分，"
                "并突出申请支持起诉的必要性。"
            ),
            "aid": (
                "请确保文书严格包含“法律援助申请信息表”标题、申请人信息、申请事项、案件概述、拟提交证据、填报日期六个部分，"
                "保持申请材料风格。"
            ),
        }
        return prompt_map.get(doc_type, "请保持法律文书固定结构。")
