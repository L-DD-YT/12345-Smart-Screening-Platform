from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeSnippet:
    category: str
    title: str
    keywords: tuple[str, ...]
    content: str


@dataclass(frozen=True)
class StatuteEntry:
    """Structured statutory reference for a public-interest domain."""
    domain: str
    code: str
    statute_no: str
    title: str
    summary: str
    keywords: tuple[str, ...] = ()
    source: str = "中华人民共和国法律法规"


@dataclass(frozen=True)
class CaseEntry:
    """Typical case reference for closed-loop assisted judgement."""
    domain: str
    code: str
    title: str
    location: str
    summary: str
    key_points: tuple[str, ...]
    outcome: str = ""


@dataclass(frozen=True)
class RegulatorEntry:
    """Regulatory duty mapping for a domain."""
    domain: str
    regulator: str
    duties: tuple[str, ...]
    related_statutes: tuple[str, ...] = ()


QUESTION_CATEGORIES = {
    "欠薪追索": ("欠薪", "工资", "拖欠", "讨薪", "薪资"),
    "未签劳动合同": ("未签", "没签合同", "劳动合同", "未签劳动合同"),
    "劳动关系认定": ("劳动关系", "工牌", "入职记录", "工作群", "考勤"),
    "仲裁诉讼": ("仲裁", "起诉", "法院", "诉讼", "立案"),
    "工伤赔偿": ("工伤", "受伤", "事故", "赔偿"),
    "支持起诉": ("支持起诉", "检察", "起诉帮助"),
    "法律援助": ("法律援助", "援助", "律师帮助"),
    "公益诉讼": ("公益诉讼", "公共利益", "生态环境", "消费者权益", "文物保护", "控烟"),
}


KNOWLEDGE_SNIPPETS = [
    KnowledgeSnippet(
        category="欠薪追索",
        title="拖欠劳动报酬维权路径",
        keywords=("欠薪", "工资", "拖欠", "报酬"),
        content="拖欠劳动报酬争议应优先固定欠薪事实、劳动关系和欠付金额，再结合协商、劳动监察投诉、劳动仲裁、诉讼等程序逐步推进。",
    ),
    KnowledgeSnippet(
        category="未签劳动合同",
        title="未签劳动合同证据规则",
        keywords=("未签", "合同", "劳动合同"),
        content="未签订书面劳动合同不当然否定劳动关系。工资流水、考勤记录、工牌、工作群聊天、同事证言、施工现场照片等均可用于证明劳动关系。",
    ),
    KnowledgeSnippet(
        category="劳动关系认定",
        title="劳动关系认定常见证明",
        keywords=("劳动关系", "工牌", "考勤", "入职"),
        content="劳动关系认定通常围绕管理从属性、报酬支付、工作内容安排展开，应重点准备入职通知、工牌、考勤、工资支付凭证、工作群记录等材料。",
    ),
    KnowledgeSnippet(
        category="仲裁诉讼",
        title="劳动争议程序顺序",
        keywords=("仲裁", "诉讼", "法院"),
        content="劳动争议通常遵循先仲裁后诉讼的程序路径。未经过劳动仲裁的，大多数劳动报酬争议不能直接起诉，应先向劳动争议仲裁委员会申请仲裁。",
    ),
    KnowledgeSnippet(
        category="工伤赔偿",
        title="工伤类案件处理重点",
        keywords=("工伤", "事故", "赔偿"),
        content="工伤类争议应优先固定受伤经过、诊疗记录、劳动关系材料，并注意工伤认定、劳动能力鉴定和赔偿请求的衔接。",
    ),
    KnowledgeSnippet(
        category="支持起诉",
        title="支持起诉适用场景",
        keywords=("支持起诉", "检察", "起诉帮助"),
        content="对弱势劳动者维权能力不足、涉及基本生存权益且符合法定条件的案件，可以考虑申请检察机关支持起诉，以强化诉讼维权能力。",
    ),
    KnowledgeSnippet(
        category="法律援助",
        title="法律援助适用场景",
        keywords=("法律援助", "援助", "律师"),
        content="对于经济困难、维权能力较弱、涉及劳动报酬追索等事项的劳动者，可以根据当地法律援助条件申请法律援助服务。",
    ),
    KnowledgeSnippet(
        category="公益诉讼",
        title="公益诉讼线索审查要点",
        keywords=("公益诉讼", "公共利益", "不特定多数人"),
        content="公益诉讼线索审查应重点关注受损利益是否涉及不特定多数人或者国家利益，并结合点位、持续时间、重复投诉频次、行政机关履职情况进行综合判断。",
    ),
    KnowledgeSnippet(
        category="公益诉讼",
        title="生态环境与公共安全治理要点",
        keywords=("生态环境", "公共安全", "河道污染", "消防通道", "食品安全"),
        content="生态环境、公共安全、食品药品安全等公益线索通常需要固定污染或风险点位、受影响范围、投诉趋势和监管职责主体，以判断是否存在持续性公共利益受损。",
    ),
    KnowledgeSnippet(
        category="综合",
        title="证据组织原则",
        keywords=("证据", "材料", "证明"),
        content="劳动争议中应区分整理主体身份材料、劳动关系材料、工资欠付材料、沟通催讨材料和程序性材料，并优先补强最能证明核心争议事实的证据。",
    ),
]


CATEGORY_EVIDENCE_REQUIREMENTS = {
    "欠薪追索": {
        "required": ["身份证明", "劳动关系证明", "工资欠付证明", "沟通催讨记录"],
        "priority": ["工资欠付证明", "劳动关系证明", "沟通催讨记录"],
    },
    "未签劳动合同": {
        "required": ["身份证明", "工资流水", "考勤记录", "工牌或工作群记录", "沟通催讨记录"],
        "priority": ["工资流水", "考勤记录", "工牌或工作群记录"],
    },
    "劳动关系认定": {
        "required": ["身份证明", "工牌或工作证", "考勤记录", "工资支付记录", "工作安排记录"],
        "priority": ["工牌或工作证", "考勤记录", "工资支付记录"],
    },
    "仲裁诉讼": {
        "required": ["身份证明", "劳动关系证明", "工资欠付证明", "仲裁材料或投诉记录"],
        "priority": ["仲裁材料或投诉记录", "工资欠付证明", "劳动关系证明"],
    },
    "工伤赔偿": {
        "required": ["身份证明", "病历和诊断证明", "事故经过说明", "劳动关系证明"],
        "priority": ["病历和诊断证明", "事故经过说明", "劳动关系证明"],
    },
    "支持起诉": {
        "required": ["身份证明", "劳动关系证明", "工资欠付证明", "维权困难说明"],
        "priority": ["工资欠付证明", "劳动关系证明", "维权困难说明"],
    },
    "法律援助": {
        "required": ["身份证明", "劳动关系证明", "工资欠付证明", "经济困难或援助申请材料"],
        "priority": ["经济困难或援助申请材料", "工资欠付证明", "劳动关系证明"],
    },
    "公益诉讼": {
        "required": ["具体点位信息", "受影响范围说明", "重复投诉或趋势材料", "行政机关处理情况"],
        "priority": ["具体点位信息", "受影响范围说明", "行政机关处理情况"],
    },
}


EVIDENCE_KEYWORDS = {
    "身份证明": ("身份证", "身份信息", "实名"),
    "劳动关系证明": ("劳动关系", "劳动合同", "入职", "录用", "工作安排"),
    "工资欠付证明": ("工资流水", "转账", "欠薪", "工资单", "银行流水", "金额"),
    "沟通催讨记录": ("微信", "聊天", "催款", "催讨", "录音", "短信"),
    "考勤记录": ("考勤", "打卡", "出勤", "签到"),
    "工牌或工作群记录": ("工牌", "工作证", "工作群", "群聊"),
    "工作安排记录": ("工作安排", "派工", "班组", "项目经理"),
    "仲裁材料或投诉记录": ("仲裁", "仲裁申请", "投诉", "监察", "回执"),
    "病历和诊断证明": ("病历", "诊断", "住院", "门诊", "伤情"),
    "事故经过说明": ("事故", "受伤", "经过", "现场"),
    "维权困难说明": ("困难", "无力", "不会维权", "帮助"),
    "经济困难或援助申请材料": ("困难证明", "低保", "援助", "经济困难"),
    "具体点位信息": ("地址", "地点", "点位", "河道", "市场", "小区"),
    "受影响范围说明": ("周边居民", "多人", "群众", "不特定多数人", "公共利益"),
    "重复投诉或趋势材料": ("多次投诉", "重复投诉", "反复投诉", "长期存在"),
    "行政机关处理情况": ("整改", "核查", "回复", "办理结果", "是否解决"),
}


# === Structured statute / case / regulator catalogues ===
STATUTE_CATALOG: tuple[StatuteEntry, ...] = (
    StatuteEntry(
        domain="生态环境和资源保护",
        code="ENV-001",
        statute_no="《中华人民共和国环境保护法》第六条",
        title="一切单位和个人都有保护环境的义务",
        summary="一切单位和个人都有保护环境的义务，地方各级政府对本行政区域的环境质量负责。",
        keywords=("污染", "排放", "公共环境", "整治"),
    ),
    StatuteEntry(
        domain="生态环境和资源保护",
        code="ENV-002",
        statute_no="《中华人民共和国民事诉讼法》第五十八条",
        title="环境污染等损害社会公共利益情形的检察公益诉讼",
        summary="对污染环境、侵害众多消费者合法权益等损害社会公共利益的行为，检察机关可以提起公益诉讼。",
        keywords=("公益诉讼", "公共利益", "环境污染"),
    ),
    StatuteEntry(
        domain="食品药品安全",
        code="FOODDRUG-001",
        statute_no="《中华人民共和国食品安全法》第一百四十一条",
        title="对违反食品安全法律法规的行政处罚",
        summary="违反食品安全法律法规生产经营食品的，由县级以上人民政府食品安全监督管理部门依法予以处罚。",
        keywords=("食品安全", "无证经营", "处罚"),
    ),
    StatuteEntry(
        domain="安全生产",
        code="SAFETY-001",
        statute_no="《中华人民共和国安全生产法》第三十二条",
        title="生产经营单位安全生产职责",
        summary="生产经营单位的主要负责人对本单位的安全生产工作全面负责，并应当配备必要的安全生产条件。",
        keywords=("安全生产", "事故隐患", "安全设施"),
    ),
    StatuteEntry(
        domain="未成年人保护",
        code="MINOR-001",
        statute_no="《中华人民共和国未成年人保护法》第一百零六条",
        title="未成年人合法权益受到侵害的检察公益诉讼",
        summary="未成年人合法权益受到侵害且涉及公共利益的，检察机关有权提起公益诉讼。",
        keywords=("未成年人", "公共利益", "校外培训"),
    ),
    StatuteEntry(
        domain="个人信息保护",
        code="PRIVACY-001",
        statute_no="《中华人民共和国个人信息保护法》第七十条",
        title="个人信息处理者侵害公益的检察公益诉讼",
        summary="个人信息处理者违反规定处理个人信息侵害众多个人权益的，检察机关有权提起公益诉讼。",
        keywords=("个人信息", "信息泄露", "公益诉讼"),
    ),
    StatuteEntry(
        domain="国有财产保护",
        code="STATE-001",
        statute_no="《中华人民共和国行政诉讼法》第二十五条第四款",
        title="国有财产保护领域行政公益诉讼",
        summary="对在国有财产保护等领域负有监督管理职责的行政机关违法行使职权或者不作为，致使国家利益受到侵害的，检察机关可提起行政公益诉讼。",
        keywords=("国有财产", "国家利益", "行政公益诉讼"),
    ),
    StatuteEntry(
        domain="国有土地使用权出让",
        code="LAND-001",
        statute_no="《中华人民共和国行政诉讼法》第二十五条第四款",
        title="国有土地使用权出让领域行政公益诉讼",
        summary="对国有土地使用权出让领域行政机关怠于履职导致国家利益受到侵害的情形，检察机关可提起行政公益诉讼。",
        keywords=("土地出让", "违法占地", "行政公益诉讼"),
    ),
    StatuteEntry(
        domain="妇女权益保障",
        code="WOMEN-001",
        statute_no="《中华人民共和国妇女权益保障法》第七十七条",
        title="侵害妇女权益的检察公益诉讼",
        summary="侵害妇女平等权利、人身权利、财产权利等情形，损害社会公共利益的，检察机关可提起公益诉讼。",
        keywords=("妇女权益", "性骚扰", "就业歧视"),
    ),
    StatuteEntry(
        domain="无障碍环境建设",
        code="ACCESS-001",
        statute_no="《中华人民共和国无障碍环境建设法》第六十二条",
        title="无障碍环境建设领域公益诉讼",
        summary="无障碍设施建设、改造维护中存在损害公共利益情形的，检察机关可提起公益诉讼。",
        keywords=("无障碍", "盲道", "残障设施"),
    ),
    StatuteEntry(
        domain="文物和文化遗产保护",
        code="HERITAGE-001",
        statute_no="《中华人民共和国文物保护法》（修订相关条款）",
        title="文物和文化遗产保护领域公益诉讼",
        summary="侵害文物及文化遗产、损害社会公共利益的违法行为，检察机关可提起公益诉讼。",
        keywords=("文物保护", "古建筑", "文保单位"),
    ),
    StatuteEntry(
        domain="英雄烈士保护",
        code="HERO-001",
        statute_no="《中华人民共和国英雄烈士保护法》第二十五条",
        title="英雄烈士保护领域公益诉讼",
        summary="侵害英雄烈士姓名、肖像、名誉、荣誉的行为，检察机关可提起公益诉讼。",
        keywords=("英雄烈士", "英烈名誉", "烈士陵园"),
    ),
)


CASE_CATALOG: tuple[CaseEntry, ...] = (
    CaseEntry(
        domain="生态环境和资源保护",
        code="CASE-ENV-001",
        title="某市河道污染整治行政公益诉讼",
        location="某市某区",
        summary="居民多次投诉某河道污水直排，多年未整改，检察机关提起行政公益诉讼督促属地管理部门履职。",
        key_points=(
            "围绕排污点位、影响范围、监管部门履职过程取证",
            "通过群众反映材料、监测数据、整改记录构成完整证据链",
            "诉前检察建议未整改后转入起诉",
        ),
        outcome="行政机关全面整改，公益受损得以修复",
    ),
    CaseEntry(
        domain="食品药品安全",
        code="CASE-FOOD-001",
        title="校园周边无证食品摊点公益诉讼",
        location="某市某区",
        summary="校园周边长期存在无证流动食品摊点，损害不特定多数未成年人合法权益。",
        key_points=(
            "结合家长投诉、监管巡查记录、市场监管处罚记录形成证据",
            "梳理同一区域、同类问题的高频投诉",
            "联合教育、市场监管、城管等多部门进行整改",
        ),
        outcome="无证摊点被取缔，建立长效巡查机制",
    ),
    CaseEntry(
        domain="未成年人保护",
        code="CASE-MINOR-001",
        title="校外培训机构虚假宣传与退费难公益诉讼",
        location="某市某区",
        summary="培训机构利用预付费方式违规收费，无法退费，损害多名未成年学员及家长权益。",
        key_points=(
            "重点收集合同、转账记录、群体投诉、退费拒绝记录",
            "评估是否具有不特定多数人受损特征",
            "配合教育部门、市场监管部门联合处置",
        ),
        outcome="责令清退、处罚并纳入信用监管",
    ),
    CaseEntry(
        domain="安全生产",
        code="CASE-SAFETY-001",
        title="施工现场违规作业损害公共安全公益诉讼",
        location="某市某区",
        summary="工地脚手架坍塌伤及行人，相关安全监管部门怠于履职。",
        key_points=(
            "围绕施工许可、安全检查记录、整改通知执行情况取证",
            "评估事故风险持续存在的客观证据",
            "对监管部门履职情况进行评估",
        ),
        outcome="责令停工整改并依法追责",
    ),
    CaseEntry(
        domain="个人信息保护",
        code="CASE-PRIVACY-001",
        title="物业违规收集业主人脸信息公益诉讼",
        location="某市某区",
        summary="物业未取得业主同意强制采集人脸信息，损害不特定多数人合法权益。",
        key_points=(
            "收集物业告知方式、信息留存周期、加密措施证据",
            "评估同类小区是否存在普遍化情形",
            "推动行业整改并发出检察建议",
        ),
        outcome="物业整改并删除违规信息",
    ),
)


REGULATOR_CATALOG: tuple[RegulatorEntry, ...] = (
    RegulatorEntry(
        domain="生态环境和资源保护",
        regulator="生态环境局",
        duties=("污染防治监督", "排污许可监管", "环境质量监测", "环境违法行为查处"),
        related_statutes=("《环境保护法》", "《大气污染防治法》", "《水污染防治法》"),
    ),
    RegulatorEntry(
        domain="食品药品安全",
        regulator="市场监督管理局",
        duties=("食品生产经营许可", "食品药品安全检查", "违法广告查处", "无证经营整治"),
        related_statutes=("《食品安全法》", "《药品管理法》"),
    ),
    RegulatorEntry(
        domain="未成年人保护",
        regulator="教育委员会、公安分局、市场监督管理局",
        duties=("校园周边治理", "校外培训监管", "未成年人合法权益保护", "网络环境净化"),
        related_statutes=("《未成年人保护法》", "《家庭教育促进法》"),
    ),
    RegulatorEntry(
        domain="安全生产",
        regulator="应急管理局",
        duties=("生产安全事故隐患排查", "建筑施工安全监管", "安全生产责任落实"),
        related_statutes=("《安全生产法》", "《消防法》"),
    ),
    RegulatorEntry(
        domain="个人信息保护",
        regulator="公安分局、网信办",
        duties=("个人信息处理监管", "网络安全审查", "信息泄露事件处置"),
        related_statutes=("《个人信息保护法》", "《网络安全法》"),
    ),
    RegulatorEntry(
        domain="国有财产保护",
        regulator="财政局、国资委",
        duties=("国有资产监督管理", "财政资金使用监督", "资产流失防范"),
        related_statutes=("《行政诉讼法》第二十五条第四款",),
    ),
    RegulatorEntry(
        domain="国有土地使用权出让",
        regulator="规划和自然资源委员会、住房和城乡建设委员会",
        duties=("土地出让监管", "违法用地查处", "闲置土地处置"),
        related_statutes=("《土地管理法》", "《城乡规划法》"),
    ),
    RegulatorEntry(
        domain="妇女权益保障",
        regulator="妇联、人力资源和社会保障局",
        duties=("妇女权益保障", "就业平等执法", "性骚扰防治"),
        related_statutes=("《妇女权益保障法》",),
    ),
    RegulatorEntry(
        domain="无障碍环境建设",
        regulator="住房和城乡建设委员会、残联",
        duties=("无障碍设施建设", "公共服务无障碍化", "无障碍设施监督"),
        related_statutes=("《无障碍环境建设法》",),
    ),
    RegulatorEntry(
        domain="文物和文化遗产保护",
        regulator="文物局、文化和旅游局",
        duties=("文物保护单位监管", "文化遗产保护", "违法违规修缮整治"),
        related_statutes=("《文物保护法》",),
    ),
    RegulatorEntry(
        domain="英雄烈士保护",
        regulator="退役军人事务局",
        duties=("烈士纪念设施保护", "英烈名誉保护", "英烈宣传纪念"),
        related_statutes=("《英雄烈士保护法》",),
    ),
)


class LegalKnowledgeService:
    """Lightweight legal knowledge retrieval and evidence analysis."""

    def classify_question(self, question: str) -> str:
        for category, keywords in QUESTION_CATEGORIES.items():
            if any(keyword in question for keyword in keywords):
                return category
        return "欠薪追索"

    def retrieve(self, question: str, category: str, top_k: int = 4) -> list[dict]:
        scored: list[tuple[int, KnowledgeSnippet]] = []
        for snippet in KNOWLEDGE_SNIPPETS:
            score = 0
            if snippet.category == category:
                score += 3
            score += sum(1 for keyword in snippet.keywords if keyword in question)
            if score > 0:
                scored.append((score, snippet))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "category": item.category,
                "title": item.title,
                "content": item.content,
            }
            for _, item in scored[:top_k]
        ]

    def analyze_evidence(self, text: str, category: str) -> dict:
        requirements = CATEGORY_EVIDENCE_REQUIREMENTS.get(category, CATEGORY_EVIDENCE_REQUIREMENTS["欠薪追索"])
        existing = []

        for evidence_name, keywords in EVIDENCE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                existing.append(evidence_name)

        required = requirements["required"]
        existing_unique = [item for item in required if item in existing]
        missing = [item for item in required if item not in existing_unique]
        priority = [item for item in requirements["priority"] if item in missing or item not in existing_unique]
        if not priority:
            priority = requirements["priority"][:]

        if not existing_unique:
            existing_unique = ["暂未识别到明确证据，建议先补充基础材料"]

        return {
            "existing_evidence": existing_unique,
            "missing_evidence": missing,
            "priority_evidence": priority[:3],
        }

    def build_public_interest_guidance(self, *, legal_domain: str, warning_level: str, public_interest_level: str) -> dict:
        snippets = self.retrieve(f"{legal_domain} 公益诉讼 公共利益", "公益诉讼", top_k=3)
        action_lines = []
        if public_interest_level == "公益":
            action_lines.append("建议围绕不特定多数人受影响范围、持续时间和监管职责主体开展核查。")
        else:
            action_lines.append("建议先核实是否确实涉及不特定多数人或国家利益，再决定是否按公益诉讼线索处理。")
        if warning_level in {"中", "高"}:
            action_lines.append("已出现中高等级预警，建议优先核查是否存在久拖未决或行政机关履职异常。")
        if legal_domain:
            action_lines.append(f"当前线索可优先对照“{legal_domain}”领域的监管职责和认定标准。")
        return {
            "references": snippets,
            "action_lines": action_lines[:4],
        }

    # ------------- structured retrieval (clue → statute / case / regulator) -------------

    def retrieve_statutes(self, *, domain: str, complaint_text: str, top_k: int = 4) -> list[dict]:
        scored: list[tuple[int, StatuteEntry]] = []
        for entry in STATUTE_CATALOG:
            score = 0
            if domain and entry.domain == domain:
                score += 4
            score += sum(1 for keyword in entry.keywords if keyword and keyword in complaint_text)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "code": entry.code,
                "domain": entry.domain,
                "statute_no": entry.statute_no,
                "title": entry.title,
                "summary": entry.summary,
                "source": entry.source,
            }
            for _, entry in scored[:top_k]
        ]

    def retrieve_cases(self, *, domain: str, complaint_text: str, top_k: int = 3) -> list[dict]:
        scored: list[tuple[int, CaseEntry]] = []
        for entry in CASE_CATALOG:
            score = 0
            if domain and entry.domain == domain:
                score += 4
            score += sum(1 for token in entry.key_points if token and token in complaint_text)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "code": entry.code,
                "domain": entry.domain,
                "title": entry.title,
                "location": entry.location,
                "summary": entry.summary,
                "key_points": list(entry.key_points),
                "outcome": entry.outcome,
            }
            for _, entry in scored[:top_k]
        ]

    def retrieve_regulators(self, *, domain: str) -> list[dict]:
        results = []
        for entry in REGULATOR_CATALOG:
            if domain and entry.domain == domain:
                results.append(
                    {
                        "domain": entry.domain,
                        "regulator": entry.regulator,
                        "duties": list(entry.duties),
                        "related_statutes": list(entry.related_statutes),
                    }
                )
        return results

    def estimate_prosecution_potential(self, record) -> dict:
        """Lightweight scoring of how likely a clue can be turned into a real case."""
        score = 0.2
        reasons: list[str] = []
        public_interest = getattr(record, "public_interest_level", "待复核")
        warning_level = getattr(record, "warning_level", "无")
        duplicate_count = getattr(record, "duplicate_count", 1) or 1
        duration_days = getattr(record, "duration_days", 0) or 0
        has_location = bool(getattr(record, "has_location", False))
        domain_confidence = float(getattr(record, "domain_confidence", 0.0) or 0.0)
        legal_domain = getattr(record, "legal_domain", "") or ""

        if public_interest == "公益":
            score += 0.25
            reasons.append("已被判定为公益属性")
        if warning_level == "高":
            score += 0.18
            reasons.append("当前为高等级预警工单")
        elif warning_level == "中":
            score += 0.10
        if duplicate_count >= 5:
            score += 0.18
            reasons.append(f"重复投诉达到 {duplicate_count} 次")
        elif duplicate_count >= 3:
            score += 0.10
            reasons.append(f"重复投诉达到 {duplicate_count} 次")
        if duration_days >= 30:
            score += 0.10
            reasons.append(f"问题持续 {duration_days} 天未化解")
        if has_location:
            score += 0.06
            reasons.append("已识别明确点位")
        if domain_confidence >= 0.7 and legal_domain:
            score += 0.08
            reasons.append(f"法定领域识别置信度较高（{round(domain_confidence * 100, 1)}%）")
        if (getattr(record, "performance_anomaly_level", "无") or "无") in {"中", "高"}:
            score += 0.10
            reasons.append("存在行政机关履职异常迹象")

        bounded = round(min(0.95, score), 4)
        if bounded >= 0.7:
            label = "高"
        elif bounded >= 0.5:
            label = "中"
        else:
            label = "低"
        if not reasons:
            reasons.append("当前线索证据较薄弱，建议补充材料后再评估。")
        return {
            "score": bounded,
            "label": label,
            "reasons": reasons[:5],
        }

    def build_assistant_judgement(self, record) -> dict:
        """Aggregate statutes / cases / regulators / evidence / potential into a single payload."""
        domain = getattr(record, "legal_domain", "") or ""
        complaint_text = getattr(record, "complaint_text", "") or ""
        category = "公益诉讼" if (
            getattr(record, "category", "") == "公益诉讼"
            or getattr(record, "public_interest_level", "") == "公益"
        ) else getattr(record, "category", "") or "欠薪追索"

        statutes = self.retrieve_statutes(domain=domain, complaint_text=complaint_text)
        cases = self.retrieve_cases(domain=domain, complaint_text=complaint_text)
        regulators = self.retrieve_regulators(domain=domain)
        evidence = self.analyze_evidence(complaint_text, category)
        guidance = self.build_public_interest_guidance(
            legal_domain=domain,
            warning_level=getattr(record, "warning_level", "无") or "无",
            public_interest_level=getattr(record, "public_interest_level", "待复核") or "待复核",
        )
        prosecution = self.estimate_prosecution_potential(record)

        return {
            "domain": domain,
            "category": category,
            "statutes": statutes,
            "cases": cases,
            "regulators": regulators,
            "evidence_analysis": evidence,
            "investigation_focus": guidance["action_lines"],
            "knowledge_snippets": guidance["references"],
            "prosecution_potential": prosecution,
        }
