from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable


PROC_CATEGORIES: tuple[str, ...] = (
    "民事支持起诉",
    "行政违法监督",
    "公益诉讼",
    "刑事犯罪线索",
    "其他",
)


# Standardized public-interest domain catalog used after public-interest detection.
@dataclass(frozen=True)
class LegalDomainDefinition:
    code: str
    name: str
    parent_category: str
    keywords: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    scene_terms: tuple[str, ...] = ()
    object_terms: tuple[str, ...] = ()
    consequence_terms: tuple[str, ...] = ()
    typical_regulators: tuple[str, ...] = ()
    enabled: bool = True
    version: str = "v1"
    weight: float = 1.0


LEGAL_DOMAIN_DEFINITIONS: tuple[LegalDomainDefinition, ...] = (
    LegalDomainDefinition(
        code="ENV",
        name="生态环境和资源保护",
        parent_category="公益诉讼法定领域",
        keywords=("污水", "河道污染", "垃圾堆放", "黑臭水体", "非法倾倒", "油烟扰民", "扬尘", "异味", "噪声污染", "工业废气", "非法采砂", "非法采矿", "积水", "污水外溢", "排水不畅"),
        aliases=("环境污染", "生态破坏", "环境破坏", "资源破坏"),
        scene_terms=("河道", "水体", "林地", "耕地", "矿山", "土壤污染", "建筑垃圾", "固体废物", "生态修复", "排水沟", "排水管网"),
        object_terms=("生态环境", "自然资源", "饮用水源", "林木", "耕地", "湿地", "排水设施"),
        consequence_terms=("污染", "超标", "破坏", "偷排", "直排", "非法倾倒", "积水", "外溢", "堵塞"),
        typical_regulators=("生态环境局", "城市管理综合行政执法局", "水务局"),
        weight=1.12,
    ),
    LegalDomainDefinition(
        code="FOODDRUG",
        name="食品药品安全",
        parent_category="公益诉讼法定领域",
        keywords=("食品安全", "餐饮卫生", "过期食品", "假药", "药品安全", "无证经营", "食品过期", "黑作坊", "非法添加", "保健品骗局"),
        aliases=("食药安全", "食品药品"),
        scene_terms=("后厨", "餐馆", "学校食堂", "药店", "外卖", "冷链", "熟食"),
        object_terms=("食品", "药品", "保健品", "餐饮", "药械"),
        consequence_terms=("变质", "过期", "假冒", "有毒有害", "不符合标准", "无证销售"),
        typical_regulators=("市场监督管理局", "卫生健康委员会"),
        weight=1.15,
    ),
    LegalDomainDefinition(
        code="SAFETY",
        name="安全生产",
        parent_category="公益诉讼法定领域",
        keywords=("消防通道", "井盖破损", "电梯故障", "燃气泄漏", "危化品", "高空坠物", "施工安全", "脚手架", "塌方", "安全隐患", "通道占用", "疏散通道"),
        aliases=("生产安全", "公共安全隐患"),
        scene_terms=("工地", "厂房", "仓库", "特种设备", "充电桩", "燃气管道", "消防设施", "安全出口"),
        object_terms=("公共安全", "消防安全", "生产安全", "人身安全", "疏散通道"),
        consequence_terms=("堵塞", "泄漏", "坠落", "爆燃", "失修", "未验收", "占用", "封闭"),
        typical_regulators=("应急管理局", "住房和城乡建设委员会"),
        weight=1.12,
    ),
    LegalDomainDefinition(
        code="STATE_ASSET",
        name="国有财产保护",
        parent_category="公益诉讼法定领域",
        keywords=("国有资产", "财政资金", "公共资金", "骗取补贴", "资产流失", "国资流失", "专项资金", "国有财产"),
        aliases=("国有财产", "财政资金流失"),
        scene_terms=("补贴资金", "政府采购", "公共资金", "专项经费", "国资经营"),
        object_terms=("国有资产", "财政资金", "公共资金", "国有财产"),
        consequence_terms=("流失", "骗取", "套取", "侵占", "挪用"),
        typical_regulators=("财政局", "国资委"),
        weight=1.08,
    ),
    LegalDomainDefinition(
        code="LAND_USE",
        name="国有土地使用权出让",
        parent_category="公益诉讼法定领域",
        keywords=("土地出让", "违法占地", "闲置土地", "违规供地", "改变土地用途", "非法转让土地", "未批先建"),
        aliases=("土地出让", "国有土地"),
        scene_terms=("工业用地", "建设用地", "供地", "出让合同", "土地闲置", "土地用途"),
        object_terms=("国有土地使用权", "土地资源"),
        consequence_terms=("违规出让", "低价出让", "闲置", "违法占用", "擅自改变用途"),
        typical_regulators=("规划和自然资源委员会", "住房和城乡建设委员会"),
        weight=1.08,
    ),
    LegalDomainDefinition(
        code="MINOR",
        name="未成年人保护",
        parent_category="公益诉讼法定领域",
        keywords=("未成年人", "校园周边", "校外培训", "未成年", "学生群体", "校园欺凌", "辍学", "未成年人入住"),
        aliases=("未成年保护", "学生保护"),
        scene_terms=("学校", "幼儿园", "托管机构", "培训机构", "网吧", "文身", "烟酒售卖"),
        object_terms=("未成年人", "学生"),
        consequence_terms=("侵害", "诱导", "失管", "违规接纳", "违法经营"),
        typical_regulators=("教育委员会", "公安分局"),
        weight=1.1,
    ),
    LegalDomainDefinition(
        code="PRIVACY",
        name="个人信息保护",
        parent_category="公益诉讼法定领域",
        keywords=("个人信息", "隐私泄露", "信息倒卖", "人脸识别", "手机号泄露", "数据泄露", "APP过度收集"),
        aliases=("信息保护", "隐私保护"),
        scene_terms=("快递单", "人脸门禁", "APP", "小程序", "数据库", "摄像头"),
        object_terms=("个人信息", "隐私", "数据"),
        consequence_terms=("泄露", "倒卖", "收集", "滥用", "非法提供"),
        typical_regulators=("公安分局", "网信办"),
        weight=1.08,
    ),
    LegalDomainDefinition(
        code="WOMEN",
        name="妇女权益保障",
        parent_category="公益诉讼法定领域",
        keywords=("妇女权益", "女职工", "性骚扰", "就业歧视", "家暴", "产假待遇", "生育权益"),
        aliases=("妇女保障", "女性权益"),
        scene_terms=("招聘", "职场", "孕期", "产假", "哺乳期", "公共场所"),
        object_terms=("妇女", "女职工", "女性"),
        consequence_terms=("歧视", "侵害", "骚扰", "克扣", "限制"),
        typical_regulators=("妇联", "人力资源和社会保障局"),
        weight=1.05,
    ),
    LegalDomainDefinition(
        code="ACCESS",
        name="无障碍环境建设",
        parent_category="公益诉讼法定领域",
        keywords=("无障碍", "盲道", "轮椅通道", "无障碍坡道", "无障碍卫生间", "残障设施", "电梯无障碍"),
        aliases=("无障碍建设",),
        scene_terms=("地铁站出入口", "政务大厅入口", "医院出入口", "无障碍卫生间", "坡道区域", "盲道区域"),
        object_terms=("无障碍设施", "残疾人通行", "老年人通行", "轮椅通行", "盲人通行"),
        consequence_terms=("缺失", "被占用", "损坏", "中断", "无法通行", "通行受阻"),
        typical_regulators=("住房和城乡建设委员会", "残联"),
        weight=1.05,
    ),
    LegalDomainDefinition(
        code="HERITAGE",
        name="文物保护",
        parent_category="公益诉讼法定领域",
        keywords=("文物保护", "文化遗产", "古建筑", "文保单位", "不可移动文物", "非遗", "历史建筑"),
        aliases=("文物和文化遗产保护", "文化遗产保护"),
        scene_terms=("古树名木", "历史街区", "文物单位", "遗址", "修缮工程"),
        object_terms=("文物", "文化遗产", "古建筑"),
        consequence_terms=("破坏", "拆除", "损毁", "违规修缮", "占压"),
        typical_regulators=("文物局", "文化和旅游局"),
        weight=1.08,
    ),
    LegalDomainDefinition(
        code="OTHER",
        name="其他",
        parent_category="公益诉讼法定领域",
        keywords=("英雄烈士", "烈士纪念设施", "反垄断", "电信诈骗", "网络诈骗", "农产品质量", "军人权益", "军属权益", "控烟", "公共场所吸烟", "商场吸烟", "厕所吸烟", "二手烟"),
        aliases=("其他公益领域",),
        scene_terms=("烈士陵园", "平台二选一", "农残超标", "优待政策", "商场卫生间", "公共厕所"),
        object_terms=(),
        consequence_terms=(),
        typical_regulators=(),
        weight=0.82,
    ),
)

LEGAL_DOMAIN_SEMANTIC_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "ENV": (
        ("水体污染", r"(?:河道|污水|水体|饮用水|自来水).{0,12}(?:污染|发黑|发臭|异味|偷排|直排|超标)"),
        ("固废垃圾扰民", r"(?:垃圾|建筑垃圾|固体废物|渣土).{0,12}(?:堆放|倾倒|乱倒|污染)"),
        ("扬尘油烟噪声", r"(?:扬尘|油烟|异味|噪声).{0,12}(?:扰民|污染|超标|严重)"),
        ("排水积水失管", r"(?:排水|排水沟|排水管网|路面积水|污水外溢).{0,12}(?:堵塞|不畅|积水|外溢|异味)"),
    ),
    "FOODDRUG": (
        ("餐饮食品安全", r"(?:餐馆|饭店|后厨|食堂|外卖|熟食).{0,12}(?:过期|变质|腐败|无证|卫生差|不洁)"),
        ("药品销售风险", r"(?:药店|药品|保健品).{0,12}(?:假冒|过期|无证|违规销售)"),
        ("校园食安风险", r"(?:学校|幼儿园).{0,12}(?:食堂|餐饮).{0,12}(?:卫生|变质|过期|食品安全)"),
    ),
    "SAFETY": (
        ("消防通道堵塞", r"(?:消防通道|安全出口).{0,10}(?:堵塞|被占用|封闭|锁闭)"),
        ("电梯设备故障", r"(?:电梯|扶梯|井盖|充电桩).{0,12}(?:故障|破损|失修|停运|隐患)"),
        ("燃气施工隐患", r"(?:燃气|燃气管道|工地|脚手架|高空坠物).{0,12}(?:泄漏|坠落|塌方|未整改|隐患)"),
        ("疏散通道受阻", r"(?:消防安全|通道占用|疏散通道).{0,10}(?:占用|堵塞|封闭|受阻)"),
    ),
    "STATE_ASSET": (
        ("国资财政流失", r"(?:国有资产|国资|财政资金|公共资金|专项资金).{0,12}(?:流失|侵占|挪用|骗取|套取)"),
        ("基金补贴风险", r"(?:医保基金|补贴资金|专项经费).{0,12}(?:骗取|套取|违规|流失)"),
    ),
    "LAND_USE": (
        ("土地违法占用", r"(?:土地|建设用地|工业用地).{0,12}(?:违法占地|违法建设|未批先建|违规供地)"),
        ("土地出让异常", r"(?:土地出让|供地|出让合同).{0,12}(?:低价|违规|违法|闲置)"),
    ),
    "MINOR": (
        ("未成年人经营风险", r"(?:未成年人|学生|校园周边).{0,12}(?:文身|烟酒售卖|网吧|培训机构|违规接纳)"),
        ("校园保护风险", r"(?:学校|幼儿园|托管机构|培训机构).{0,12}(?:欺凌|侵害|失管|诱导)"),
    ),
    "PRIVACY": (
        ("个人信息泄露", r"(?:个人信息|隐私|手机号|人脸信息|快递单).{0,12}(?:泄露|倒卖|滥用|非法提供)"),
        ("过度收集信息", r"(?:APP|小程序|门禁|摄像头).{0,12}(?:收集|抓取|索取).{0,8}(?:个人信息|隐私|人脸)"),
    ),
    "WOMEN": (
        ("职场妇女权益", r"(?:女职工|女性|妇女).{0,12}(?:歧视|骚扰|克扣|限制|不公平)"),
        ("生育期权益", r"(?:孕期|产假|哺乳期|生育).{0,12}(?:待遇|权益|被辞退|受限)"),
    ),
    "ACCESS": (
        ("无障碍设施受阻", r"(?:盲道|无障碍坡道|轮椅通道|无障碍卫生间).{0,12}(?:被占用|损坏|中断|无法通行|通行受阻)"),
        ("残障通行困难", r"(?:残疾人|老年人|轮椅).{0,12}(?:无法通行|进出困难|受阻).{0,8}(?:盲道|坡道|无障碍)"),
    ),
    "HERITAGE": (
        ("文物建筑损毁", r"(?:文物|古建筑|历史建筑|文保单位|遗址).{0,12}(?:损毁|拆除|破坏|违规修缮|占压)"),
        ("文化遗产风险", r"(?:文化遗产|非遗|古树名木).{0,12}(?:破坏|损坏|拆改|失修)"),
    ),
    "OTHER": (
        ("控烟公共卫生", r"(?:控烟|吸烟|抽烟|二手烟).{0,12}(?:公共厕所|商场|卫生间|楼道|写字楼|公共场所)"),
        ("英雄烈士保护", r"(?:烈士|纪念设施|陵园).{0,12}(?:破坏|占用|损坏)"),
        ("预付费消费风险", r"(?:预收费|预付费|单用途预付卡|健身卡|游泳卡|挂号与退费).{0,16}(?:退费|退款|纠纷|投诉集中|维权)"),
        ("停车秩序管理", r"(?:停车管理|停车秩序|停车位|停车场).{0,16}(?:混乱|堵塞|纠纷|管理问题)"),
        ("道路运输非法营运", r"(?:非法营运|黑车|道路运输).{0,16}(?:投诉集中|秩序混乱|运营问题)"),
        ("占道经营秩序", r"(?:占道经营|占道摆摊).{0,16}(?:秩序|通行|管理问题|投诉集中)"),
        ("养老机构服务", r"(?:养老服务|养老机构|机构服务).{0,16}(?:管理问题|服务问题|投诉集中)"),
        ("参保缴费争议", r"(?:参保缴费|社保缴费|医保报销).{0,16}(?:咨询|争议|诉求|投诉集中)"),
    ),
}

SEMANTIC_OBJECT_SLOTS: dict[str, tuple[str, ...]] = {
    "环境介质": ("河道", "污水", "垃圾", "扬尘", "油烟", "噪声", "水体", "饮用水", "自来水", "土壤", "林地", "耕地", "矿山", "固体废物", "排水", "排水沟", "排水管网", "积水"),
    "食药对象": ("食品", "药品", "后厨", "食堂", "餐馆", "饭店", "外卖", "药店", "保健品", "熟食"),
    "安全设施": ("消防通道", "安全出口", "电梯", "井盖", "燃气", "燃气管道", "脚手架", "工地", "高空坠物", "充电桩", "施工现场"),
    "国资资金": ("国有资产", "国资", "财政资金", "公共资金", "专项资金", "医保基金", "补贴资金", "专项经费"),
    "土地资源": ("土地", "建设用地", "工业用地", "土地出让", "供地", "出让合同", "土地资源"),
    "未成年群体": ("未成年人", "未成年", "学生", "校园周边", "幼儿园", "托管机构", "培训机构"),
    "个人信息": ("个人信息", "隐私", "手机号", "人脸信息", "快递单", "app", "小程序", "数据库", "摄像头"),
    "妇女权益": ("妇女", "女性", "女职工", "孕期", "产假", "哺乳期", "生育"),
    "无障碍设施": ("盲道", "无障碍坡道", "轮椅通道", "无障碍卫生间", "残疾人", "老年人", "轮椅"),
    "文物遗产": ("文物", "古建筑", "历史建筑", "文保单位", "文化遗产", "非遗", "古树名木", "遗址"),
    "控烟卫生": ("控烟", "吸烟", "抽烟", "二手烟", "公共场所吸烟"),
    "公共服务设施": ("供水", "供水管网", "排水", "污水管网", "学校食堂", "农贸市场", "公共厕所", "道路", "医院", "社区", "小区"),
    "其他公共议题": ("预收费", "预付费", "单用途预付卡", "健身卡", "游泳卡", "停车管理", "非法营运", "占道经营", "养老服务", "机构服务", "参保缴费"),
}

SEMANTIC_CONSEQUENCE_SLOTS: dict[str, tuple[str, ...]] = {
    "污染损害": ("污染", "超标", "异味", "发黑", "发臭", "扬尘", "扰民", "偷排", "直排", "黑臭"),
    "食药违规": ("过期", "变质", "腐败", "无证", "假冒", "非法添加", "不洁", "卫生差"),
    "安全隐患": ("堵塞", "封闭", "占用", "故障", "破损", "泄漏", "坠落", "塌方", "隐患", "失修"),
    "资金流失": ("流失", "侵占", "挪用", "骗取", "套取"),
    "土地违规": ("违法占地", "未批先建", "违规供地", "闲置", "低价出让", "改变土地用途"),
    "未成年侵害": ("欺凌", "侵害", "诱导", "失管", "违规接纳", "违法经营"),
    "信息侵权": ("泄露", "倒卖", "滥用", "非法提供", "过度收集"),
    "妇女侵权": ("歧视", "骚扰", "克扣", "限制", "辞退", "不公平"),
    "通行受阻": ("损坏", "中断", "无法通行", "通行受阻", "被占用"),
    "文物损毁": ("损毁", "拆除", "破坏", "违规修缮", "占压"),
    "公共卫生失管": ("吸烟", "抽烟", "二手烟"),
    "消费秩序争议": ("退费", "退款", "纠纷", "投诉集中", "管理问题", "秩序混乱"),
}

SEMANTIC_GOVERNANCE_TERMS: tuple[str, ...] = (
    "整改",
    "整治",
    "治理",
    "查处",
    "排查",
    "巡查",
    "执法",
    "监管",
    "履职",
    "监督",
    "复查",
    "关停",
    "查封",
    "移送",
    "处罚",
)

DOMAIN_SEMANTIC_SLOT_PROFILES: dict[str, dict[str, tuple[str, ...]]] = {
    "ENV": {"objects": ("环境介质", "公共服务设施"), "consequences": ("污染损害",)},
    "FOODDRUG": {"objects": ("食药对象",), "consequences": ("食药违规",)},
    "SAFETY": {"objects": ("安全设施", "公共服务设施"), "consequences": ("安全隐患",)},
    "STATE_ASSET": {"objects": ("国资资金",), "consequences": ("资金流失",)},
    "LAND_USE": {"objects": ("土地资源",), "consequences": ("土地违规",)},
    "MINOR": {"objects": ("未成年群体",), "consequences": ("未成年侵害",)},
    "PRIVACY": {"objects": ("个人信息",), "consequences": ("信息侵权",)},
    "WOMEN": {"objects": ("妇女权益",), "consequences": ("妇女侵权",)},
    "ACCESS": {"objects": ("无障碍设施",), "consequences": ("通行受阻",)},
    "HERITAGE": {"objects": ("文物遗产",), "consequences": ("文物损毁",)},
    "OTHER": {"objects": ("控烟卫生", "其他公共议题"), "consequences": ("公共卫生失管", "消费秩序争议")},
}


def list_enabled_legal_domains() -> tuple[LegalDomainDefinition, ...]:
    return tuple(item for item in LEGAL_DOMAIN_DEFINITIONS if item.enabled)


def get_legal_domain(name: str) -> LegalDomainDefinition | None:
    for definition in LEGAL_DOMAIN_DEFINITIONS:
        if definition.name == name or definition.code == name:
            return definition
    return None


CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "民事支持起诉": (
        "拖欠工资",
        "欠薪",
        "讨薪",
        "工资未发",
        "不发工资",
        "农民工工资",
        "家暴",
        "家庭暴力",
        "虐待",
        "劳动合同",
        "社保",
        "参保缴费",
    ),
    "行政违法监督": (
        "处罚太重",
        "过重处罚",
        "小过重罚",
        "罚款过高",
        "同案不同罚",
        "执法不规范",
        "乱罚款",
        "程序违法",
        "重复处罚",
        "违法建设",
        "行政检察",
    ),
    "公益诉讼": tuple(
        sorted(
            {
                keyword
                for domain in LEGAL_DOMAIN_DEFINITIONS
                for keyword in domain.keywords
                if keyword
            }
            | {"公共环境", "不特定多数人", "国家利益", "公共利益", "社会公共利益", "多人投诉", "群体反映"}
        )
    ),
    "刑事犯罪线索": ("故意伤害", "家暴致伤", "虐待儿童", "非法拘禁", "诈骗", "非法集资", "传销", "强迫交易"),
}

CASE_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "民事支持起诉": ("民事检察", "拖欠工资", "支持起诉"),
    "行政违法监督": ("行政检察", "违法建设", "行政违法监督"),
    "公益诉讼": tuple(
        ["公益诉讼", "公共利益", "国家利益", "不特定多数人"] + [domain.name for domain in LEGAL_DOMAIN_DEFINITIONS if domain.keywords]
    ),
    "刑事犯罪线索": ("刑事", "犯罪线索"),
}

ISSUE_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "民事支持起诉": ("拖欠工资", "劳动合同", "社会保险", "参保缴费"),
    "行政违法监督": ("处罚", "执法", "违法建设", "程序违法"),
    "公益诉讼": CATEGORY_KEYWORDS["公益诉讼"],
    "刑事犯罪线索": ("故意伤害", "诈骗", "非法集资"),
}

CATEGORY_PROTOTYPES: dict[str, tuple[str, ...]] = {
    "民事支持起诉": (
        "投诉内容涉及拖欠工资、农民工讨薪、家暴虐待、弱势群体维权等，适合民事支持起诉审查。",
        "工人反映项目部拖欠工资，没有劳动合同，需要检察机关支持起诉或者保护弱势群体权益。",
    ),
    "行政违法监督": (
        "企业反映行政机关存在小过重罚、同案不同罚、程序违法、执法不规范等情形。",
        "投诉围绕行政执法尺度失衡、处罚过重、重复处罚、程序不规范，适合行政违法监督。",
    ),
    "公益诉讼": (
        "投诉聚焦生态环境、食品药品、安全生产、国有资产、未成年人等公共利益受损场景。",
        "多名群众持续投诉某个地点的环境污染、消防通道堵塞、个人信息泄露或其他涉及不特定多数人的问题。",
    ),
    "刑事犯罪线索": (
        "投诉反映诈骗、非法集资、人身侵害、非法拘禁、强迫交易等疑似刑事犯罪行为。",
        "举报内容具有明显刑事违法犯罪风险，需要作为刑事犯罪线索重点核查。",
    ),
    "其他": (
        "普通民生诉求或信息不足，暂时无法直接归入涉检监督线索类别。",
        "文本没有明确的涉检语义、监督对象或犯罪风险，需要进一步人工识别。",
    ),
}

PUBLIC_INTEREST_POSITIVE_TERMS: tuple[str, ...] = (
    "多名群众",
    "周边居民",
    "不特定多数人",
    "国家利益",
    "社会公共利益",
    "公共环境",
    "公共安全",
    "群众集中反映",
    "多人投诉",
    "群体投诉",
    "群体反映",
    "公共设施",
    "公共秩序",
    "公共卫生",
    "长期存在",
    "反复投诉",
)

PUBLIC_INTEREST_NEGATIVE_TERMS: tuple[str, ...] = (
    "仅我一人",
    "我个人",
    "我自己",
    "我的工资",
    "我的房屋",
    "我家合同",
    "我家装修",
    "我家漏水",
    "我家车位",
    "个人赔偿",
    "退我",
    "赔我",
    "只影响我",
    "只涉及我家",
)

# Structured slot keywords used by the public/private interest discriminator.
PUBLIC_INTEREST_GROUP_TERMS: tuple[str, ...] = (
    "多名",
    "众多",
    "多位",
    "几十名",
    "几十位",
    "数十名",
    "上百",
    "数百",
    "周边居民",
    "全体居民",
    "广大居民",
    "全体业主",
    "全体租户",
    "群众",
    "市民",
)

PUBLIC_INTEREST_NATIONAL_TERMS: tuple[str, ...] = (
    "国家利益",
    "国家财产",
    "国有资产",
    "公共财政",
    "公共资金",
    "公共安全",
    "公共健康",
    "社会公共利益",
)

PUBLIC_INTEREST_SCOPE_TERMS: tuple[str, ...] = (
    "整条街",
    "整个小区",
    "整片区域",
    "全村",
    "整个市场",
    "园区内",
    "辖区内",
    "本街道",
    "本社区",
    "整个工地",
    "周边区域",
    "沿线商户",
    "多个小区",
)

PUBLIC_INTEREST_GOVERNANCE_TERMS: tuple[str, ...] = (
    "监管不到位",
    "履职不到位",
    "长期未整改",
    "久拖不决",
    "无人处理",
    "多部门",
    "联合执法",
    "整改",
    "排查",
    "巡查",
    "执法检查",
    "监督检查",
)

PUBLIC_INTEREST_PUBLIC_FACILITY_TERMS: tuple[str, ...] = (
    "消防通道",
    "盲道",
    "无障碍坡道",
    "垃圾站",
    "河道",
    "污水井",
    "燃气管道",
    "电梯",
    "学校食堂",
    "公共厕所",
)

PUBLIC_INTEREST_INFRASTRUCTURE_TERMS: tuple[str, ...] = (
    "供水",
    "自来水",
    "水龙头",
    "供水管网",
    "排水",
    "污水管网",
    "燃气",
    "燃气管道",
    "电梯",
    "消防设施",
    "学校食堂",
    "农贸市场",
    "小区",
    "社区",
    "医院",
    "校园周边",
    "公共停车场",
    "道路",
)

PUBLIC_INTEREST_IMPLIED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("供水污染风险", r"(?:我家|住户|居民).{0,10}(?:水龙头|自来水|供水).{0,10}(?:浑浊|发黄|异味|污染|发黑)"),
    ("医保基金治理风险", r"(?:医保报销难|医保基金|医保报销).{0,12}(?:漏洞|异常|违规|长期|管理)"),
    ("社区环境外溢风险", r"(?:我家楼下|小区周边|社区附近).{0,12}(?:油烟|污水|垃圾|扬尘|噪声|异味)"),
    ("公共安全治理风险", r"(?:楼道|小区|社区|市场|学校).{0,12}(?:消防通道|井盖|燃气|高空坠物|电梯).{0,10}(?:堵塞|破损|故障|隐患)"),
    ("个人信息外溢风险", r"(?:住户|业主|居民).{0,10}(?:人脸识别|手机号|个人信息|隐私).{0,10}(?:泄露|收集|倒卖|滥用)"),
    ("公共场所持续失管", r"(?:市场|学校|医院|景区|车站|街道|社区).{0,12}(?:长期|持续|反复).{0,12}(?:未整改|无人处理|管理不到位)"),
)

PUBLIC_INTEREST_PRIVATE_DISPUTE_TERMS: tuple[str, ...] = (
    "劳动合同纠纷",
    "借款纠纷",
    "物业费",
    "退款纠纷",
    "停车费",
    "租赁纠纷",
    "邻里纠纷",
    "房屋漏水",
    "装修纠纷",
    "合同违约",
    "赔偿款",
    "退费",
)

PUBLIC_INTEREST_PRIVATE_PATTERNS: tuple[str, ...] = (
    r"(?:要求|请求).{0,8}(?:赔偿|退款|返还|补偿)",
    r"(?:请|要求).{0,8}(?:帮我|为我|给我)解决",
    r"(?:本人|我本人|我家).{0,12}(?:损失|受损|权益)",
    r"只有我(?:家)?",
)

PUBLIC_INTEREST_STRONG_PUBLIC_TERMS: tuple[str, ...] = (
    "不特定多数人",
    "社会公共利益",
    "国家利益",
    "国有资产",
    "公共资金",
    "公共财政",
    "医保基金",
    "供水管网",
    "河道污染",
    "消防通道",
    "学校食堂",
    "盲道",
    "无障碍坡道",
    "个人信息泄露",
)

PUBLIC_INTEREST_STRONG_PRIVATE_TERMS: tuple[str, ...] = (
    "退款",
    "赔偿",
    "补偿",
    "合同违约",
    "借款纠纷",
    "邻里纠纷",
    "装修纠纷",
    "车位纠纷",
    "物业费",
    "租赁纠纷",
)

PUBLIC_INTEREST_STRONG_PUBLIC_PATTERNS: tuple[tuple[str, str], ...] = (
    ("群体投诉且长期未整改", r"(?:多个小区|周边居民|多名群众|全体业主|群众集中反映).{0,20}(?:长期|持续|反复).{0,12}(?:未整改|无人处理|监管不到位)"),
    ("公共设施持续失管", r"(?:供水管网|消防通道|学校食堂|盲道|无障碍坡道|河道).{0,16}(?:长期|持续|反复|多次).{0,12}(?:未整改|堵塞|污染|损坏|失修|故障)"),
    ("公共资金或基金治理风险", r"(?:医保基金|公共资金|公共财政|国有资产).{0,16}(?:漏洞|流失|骗取|套取|管理问题|违规)"),
    ("个人表述中的公共设施外溢", r"(?:我家|我个人|住户|业主).{0,12}(?:水龙头|自来水|供水|电梯|燃气|消防通道).{0,16}(?:浑浊|污染|故障|泄漏|堵塞|隐患)"),
)

PUBLIC_INTEREST_STRONG_PRIVATE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("单一赔偿退款诉求", r"(?:我个人|我家|本人).{0,18}(?:退款|赔偿|补偿|返还)"),
    ("典型合同或交易纠纷", r"(?:合同违约|借款纠纷|退款纠纷|租赁纠纷|装修纠纷|车位纠纷|邻里纠纷)"),
    ("仅限单户单人的私益表达", r"(?:仅我一人|只影响我|只涉及我家|只有我家)"),
)


class FeatureService:
    """Build lightweight, serializable features for batch and model pipelines."""

    feature_version = "feature-v7"

    @staticmethod
    def normalize_text(value: str) -> str:
        return re.sub(r"[\W_]+", "", value or "").lower()

    @staticmethod
    def map_manual_label_to_category(manual_label: str | None) -> str | None:
        if not manual_label:
            return None
        for category in PROC_CATEGORIES:
            if category != "其他" and category in manual_label:
                return category
        lowered = manual_label.strip()
        if lowered in PROC_CATEGORIES:
            return lowered
        return None

    @staticmethod
    def infer_category_from_external_hints(case_domain: str | None, issue_category: str | None, complaint_text: str | None = None) -> str | None:
        combined_text = " ".join(part for part in (case_domain or "", issue_category or "", complaint_text or "") if part)
        for category, keywords in CASE_DOMAIN_HINTS.items():
            if any(keyword in combined_text for keyword in keywords):
                return category
        for category, keywords in ISSUE_CATEGORY_HINTS.items():
            if any(keyword in combined_text for keyword in keywords):
                return category
        return None

    def collect_rule_counts(self, complaint_text: str) -> dict[str, int]:
        counter = Counter()
        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in complaint_text:
                    counter[category] += 1
        return {category: counter.get(category, 0) for category in PROC_CATEGORIES if category != "其他"}

    def build_rule_scores(self, complaint_text: str, matched_rules: list[dict] | None = None) -> dict[str, float]:
        counts = Counter()
        if matched_rules:
            for item in matched_rules:
                category = item.get("category")
                if category in PROC_CATEGORIES:
                    counts[category] += 1
        else:
            counts.update(self.collect_rule_counts(complaint_text))

        total = sum(counts.values())
        if not total:
            return {category: 0.0 for category in PROC_CATEGORIES}

        scores = {category: round(counts.get(category, 0) / total, 6) for category in PROC_CATEGORIES if category != "其他"}
        max_value = max(scores.values(), default=0.0)
        scores["其他"] = 1.0 - max_value if max_value < 0.35 else 0.0
        return scores

    def build_training_text(
        self,
        complaint_text: str,
        district: str | None = None,
        location_text: str | None = None,
        matched_rules: list[dict] | None = None,
    ) -> str:
        counts = self.build_rule_scores(complaint_text, matched_rules)
        location_flag = "has_location" if (location_text or district) else "no_location"
        digit_count = len(re.findall(r"\d", complaint_text))
        has_money = "has_money" if re.search(r"\d+(?:\.\d+)?\s*(万元|元)", complaint_text) else "no_money"
        tags = [
            f"rule_{category}_{int(score * 100)}"
            for category, score in counts.items()
            if category != "其他" and score > 0
        ]
        tags.extend([location_flag, has_money, f"digits_{digit_count}"])
        parts = [
            " ".join(tags),
            district or "",
            location_text or "",
            complaint_text or "",
        ]
        return " [SEP] ".join(part for part in parts if part)

    def resolve_training_label(self, manual_label: str | None, category: str | None) -> str | None:
        mapped = self.map_manual_label_to_category(manual_label)
        if mapped:
            return mapped
        if category in PROC_CATEGORIES:
            return category
        return None

    @staticmethod
    def summarize_top_scores(score_map: dict[str, float], top_k: int = 3) -> list[dict]:
        return [
            {"label": label, "score": round(score, 4)}
            for label, score in sorted(score_map.items(), key=lambda item: item[1], reverse=True)[:top_k]
        ]

    @staticmethod
    def build_semantic_corpus() -> tuple[list[str], list[str]]:
        labels: list[str] = []
        texts: list[str] = []
        for category, examples in CATEGORY_PROTOTYPES.items():
            for sample in examples:
                labels.append(category)
                texts.append(sample)
        return labels, texts

    @staticmethod
    def chunked(values: Iterable, size: int):
        batch = []
        for value in values:
            batch.append(value)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch

    @staticmethod
    def list_legal_domains() -> list[str]:
        return [item.name for item in LEGAL_DOMAIN_DEFINITIONS if item.enabled]

    @staticmethod
    def list_legal_domain_records() -> list[dict]:
        """Standardized view of the public-interest domain catalog for UI/API exposure."""
        return [
            {
                "code": item.code,
                "name": item.name,
                "parent_category": item.parent_category,
                "enabled": item.enabled,
                "version": item.version,
                "keywords": list(item.keywords),
                "aliases": list(item.aliases),
                "scene_terms": list(item.scene_terms),
                "object_terms": list(item.object_terms),
                "consequence_terms": list(item.consequence_terms),
                "typical_regulators": list(item.typical_regulators),
            }
            for item in LEGAL_DOMAIN_DEFINITIONS
        ]

    def infer_legal_domains(self, complaint_text: str) -> list[dict]:
        candidates = self.infer_domain_candidates(complaint_text)
        # Backward-compat: keep the {domain, score, matched_terms} contract.
        return [
            {
                "domain": item["name"],
                "score": item["score"],
                "matched_terms": item["matched_terms"],
            }
            for item in candidates
        ]

    def infer_domain_candidates(self, complaint_text: str) -> list[dict]:
        if not complaint_text:
            return []
        semantic_text = self._extract_semantic_text(complaint_text)
        hint_text = self._extract_domain_hint_text(complaint_text)
        semantic_slots = self._extract_semantic_slots(f"{hint_text} {semantic_text}".strip())
        candidates: list[dict] = []
        for definition in LEGAL_DOMAIN_DEFINITIONS:
            if not definition.enabled:
                continue
            keyword_hits = self._collect_unique_hits(semantic_text, definition.keywords)
            alias_hits = self._collect_unique_hits(semantic_text, definition.aliases)
            scene_hits = self._collect_unique_hits(semantic_text, definition.scene_terms)
            object_hits = self._collect_unique_hits(semantic_text, definition.object_terms)
            consequence_hits = self._collect_unique_hits(semantic_text, definition.consequence_terms)
            regulator_hits = self._collect_unique_hits(semantic_text, definition.typical_regulators)
            hint_keyword_hits = self._collect_unique_hits(hint_text, definition.keywords)
            hint_alias_hits = self._collect_unique_hits(hint_text, definition.aliases)
            hint_scene_hits = self._collect_unique_hits(hint_text, definition.scene_terms)
            semantic_pattern_hits = self._collect_pattern_hits(
                f"{hint_text} {semantic_text}".strip(),
                LEGAL_DOMAIN_SEMANTIC_PATTERNS.get(definition.code, ()),
            )
            slot_profile = DOMAIN_SEMANTIC_SLOT_PROFILES.get(definition.code, {})
            slot_object_hits = [
                label
                for label in semantic_slots["object_slots"]
                if label in set(slot_profile.get("objects", ()))
            ]
            slot_consequence_hits = [
                label
                for label in semantic_slots["consequence_slots"]
                if label in set(slot_profile.get("consequences", ()))
            ]
            slot_governance_hits = semantic_slots["governance_terms"] if (slot_object_hits or slot_consequence_hits) else []
            signal_groups = [
                keyword_hits,
                alias_hits,
                scene_hits,
                object_hits,
                consequence_hits,
                regulator_hits,
                hint_keyword_hits,
                hint_alias_hits,
                hint_scene_hits,
                semantic_pattern_hits,
                slot_object_hits,
                slot_consequence_hits,
                slot_governance_hits,
            ]
            if not any(signal_groups):
                continue
            only_generic_public_service_slot = (
                slot_object_hits
                and set(slot_object_hits).issubset({"公共服务设施"})
                and not (
                    keyword_hits
                    or alias_hits
                    or scene_hits
                    or object_hits
                    or consequence_hits
                    or regulator_hits
                    or hint_keyword_hits
                    or hint_alias_hits
                    or hint_scene_hits
                    or semantic_pattern_hits
                    or slot_consequence_hits
                )
            )
            if only_generic_public_service_slot:
                continue
            anchor_hits = keyword_hits + alias_hits + object_hits + hint_keyword_hits + hint_alias_hits + slot_object_hits
            context_group_count = sum(
                1
                for group in (
                    scene_hits,
                    consequence_hits,
                    regulator_hits,
                    hint_scene_hits,
                    semantic_pattern_hits,
                    slot_consequence_hits,
                    slot_governance_hits,
                )
                if group
            )
            has_anchor = bool(anchor_hits)
            if not has_anchor and context_group_count < 2:
                continue
            if definition.code in {"ACCESS", "HERITAGE"} and not has_anchor and context_group_count < 3:
                continue
            hit_terms = (
                keyword_hits
                + alias_hits
                + scene_hits
                + object_hits
                + consequence_hits
                + regulator_hits
                + hint_keyword_hits
                + hint_alias_hits
                + hint_scene_hits
                + semantic_pattern_hits
                + slot_object_hits
                + slot_consequence_hits
                + slot_governance_hits
            )
            score = 0.0
            score += 0.18 * min(len(keyword_hits), 3)
            score += 0.10 * min(len(alias_hits), 2)
            score += 0.05 * min(len(scene_hits), 3)
            score += 0.1 * min(len(object_hits), 2)
            score += 0.06 * min(len(consequence_hits), 3)
            score += 0.05 * min(len(regulator_hits), 2)
            score += 0.08 * min(len(hint_keyword_hits), 2)
            score += 0.05 * min(len(hint_alias_hits), 1)
            score += 0.04 * min(len(hint_scene_hits), 2)
            score += 0.14 * min(len(semantic_pattern_hits), 2)
            score += 0.12 * min(len(slot_object_hits), 2)
            score += 0.10 * min(len(slot_consequence_hits), 2)
            score += 0.06 * min(len(slot_governance_hits), 2)
            active_group_count = sum(1 for group in signal_groups if group)
            if has_anchor and context_group_count >= 1:
                score += 0.08
            if object_hits and consequence_hits:
                score += 0.06
            if slot_object_hits and slot_consequence_hits:
                score += 0.1
            if slot_governance_hits and (slot_object_hits or slot_consequence_hits):
                score += 0.06
            if (hint_keyword_hits or hint_alias_hits) and (scene_hits or consequence_hits or semantic_pattern_hits):
                score += 0.06
            if semantic_pattern_hits and (keyword_hits or object_hits or consequence_hits):
                score += 0.08
            if active_group_count >= 2:
                score += 0.08
            if active_group_count >= 3:
                score += 0.06
            if definition.code == "OTHER":
                score = max(score * 0.72, 0.28)
            score = min(0.98, score * float(definition.weight or 1.0))
            candidates.append(
                {
                    "code": definition.code,
                    "name": definition.name,
                    "parent_category": definition.parent_category,
                    "score": round(score, 4),
                    "matched_terms": hit_terms[:6],
                    "signal_summary": {
                        "keywords": keyword_hits[:4],
                        "aliases": alias_hits[:3],
                        "scenes": scene_hits[:3],
                        "objects": object_hits[:3],
                        "consequences": consequence_hits[:3],
                        "regulators": regulator_hits[:2],
                        "hint_keywords": hint_keyword_hits[:3],
                        "hint_aliases": hint_alias_hits[:2],
                        "hint_scenes": hint_scene_hits[:2],
                        "semantic_patterns": semantic_pattern_hits[:3],
                        "slot_objects": slot_object_hits[:2],
                        "slot_consequences": slot_consequence_hits[:2],
                        "slot_governance": slot_governance_hits[:2],
                    },
                    "typical_regulators": list(definition.typical_regulators),
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates

    def resolve_legal_domain_decision(self, complaint_text: str, *, fallback_to_other: bool = False) -> dict:
        """Pick the primary domain and surface conflict / co-occurring candidates."""
        candidates = self.infer_domain_candidates(complaint_text)
        if not candidates:
            if fallback_to_other:
                return self._build_other_domain_decision("公益属性已识别，但暂未形成稳定的领域信号，暂归“其他”。")
            return self.empty_legal_domain_decision()
        primary = candidates[0]
        confidence = float(primary["score"])
        conflict_flags: list[str] = []
        for other in candidates[1:3]:
            if confidence - float(other["score"]) <= 0.08:
                conflict_flags.append(
                    f"{primary['name']} 与 {other['name']} 命中度接近，建议人工复核"
                )
        if primary["code"] != "OTHER" and fallback_to_other and confidence < 0.4:
            other_decision = self._build_other_domain_decision("公益属性已识别，但具体领域信号偏弱，暂归“其他”并建议人工复核。")
            other_decision["confidence"] = round(max(confidence, 0.32), 4)
            other_decision["candidates"] = [other_decision["candidates"][0], *candidates[:4]]
            other_decision["domain_tags"] = [item["name"] for item in candidates[:4]]
            return other_decision
        return {
            "primary_domain": primary["name"],
            "primary_code": primary["code"],
            "confidence": round(confidence, 4),
            "candidates": candidates[:5],
            "conflict_flags": conflict_flags[:4],
            "domain_tags": [item["name"] for item in candidates[:5]],
        }

    def resolve_primary_legal_domain(self, complaint_text: str) -> tuple[str, list[dict]]:
        decision = self.resolve_legal_domain_decision(complaint_text)
        # Backward-compat for callers that expect (name, [matches])
        domain_matches = [
            {"domain": item["name"], "score": item["score"], "matched_terms": item["matched_terms"]}
            for item in decision["candidates"]
        ]
        return decision["primary_domain"], domain_matches

    def evaluate_public_interest(
        self,
        *,
        complaint_text: str,
        category: str,
        has_location: bool,
        duplicate_count: int,
        domain_matches: list[dict] | None = None,
        domain_decision: dict | None = None,
    ) -> dict:
        score = 0.0
        reasons: list[str] = []
        evidence: dict = {
            "group_terms": [],
            "national_terms": [],
            "scope_terms": [],
            "negative_terms": [],
            "governance_terms": [],
            "public_facility_terms": [],
            "infrastructure_terms": [],
            "private_dispute_terms": [],
            "private_patterns": [],
            "implied_public_patterns": [],
            "domain_hint_candidates": [],
            "semantic_object_slots": [],
            "semantic_consequence_slots": [],
            "semantic_governance_terms": [],
            "direct_rule_level": "",
            "direct_rule_reason": "",
            "borderline_resolution": "",
            "complainant_count": 0,
            "duration_signal": False,
            "frequency_signal": False,
            "location_signal": bool(has_location),
            "primary_domain": (domain_decision or {}).get("primary_domain", ""),
        }

        domain_matches = domain_matches or []
        positive_hits = [term for term in PUBLIC_INTEREST_POSITIVE_TERMS if term in complaint_text]
        negative_hits = [term for term in PUBLIC_INTEREST_NEGATIVE_TERMS if term in complaint_text]
        group_hits = [term for term in PUBLIC_INTEREST_GROUP_TERMS if term in complaint_text]
        national_hits = [term for term in PUBLIC_INTEREST_NATIONAL_TERMS if term in complaint_text]
        scope_hits = [term for term in PUBLIC_INTEREST_SCOPE_TERMS if term in complaint_text]
        governance_hits = [term for term in PUBLIC_INTEREST_GOVERNANCE_TERMS if term in complaint_text]
        public_facility_hits = [term for term in PUBLIC_INTEREST_PUBLIC_FACILITY_TERMS if term in complaint_text]
        infrastructure_hits = [term for term in PUBLIC_INTEREST_INFRASTRUCTURE_TERMS if term in complaint_text]
        private_dispute_hits = [term for term in PUBLIC_INTEREST_PRIVATE_DISPUTE_TERMS if term in complaint_text]
        private_pattern_hits = [pattern for pattern in PUBLIC_INTEREST_PRIVATE_PATTERNS if re.search(pattern, complaint_text)]
        implied_public_hits = [
            label for label, pattern in PUBLIC_INTEREST_IMPLIED_PATTERNS if re.search(pattern, complaint_text)
        ]
        semantic_slots = self._extract_semantic_slots(self._extract_semantic_text(complaint_text))
        domain_hint_candidates = [
            item
            for item in self.infer_domain_candidates(complaint_text)
            if item.get("code") not in {"OTHER"} and float(item.get("score", 0.0) or 0.0) >= 0.38
        ]
        strong_public_term_hits = [term for term in PUBLIC_INTEREST_STRONG_PUBLIC_TERMS if term in complaint_text]
        strong_private_term_hits = [term for term in PUBLIC_INTEREST_STRONG_PRIVATE_TERMS if term in complaint_text]
        strong_public_pattern_hits = [
            label for label, pattern in PUBLIC_INTEREST_STRONG_PUBLIC_PATTERNS if re.search(pattern, complaint_text)
        ]
        strong_private_pattern_hits = [
            label for label, pattern in PUBLIC_INTEREST_STRONG_PRIVATE_PATTERNS if re.search(pattern, complaint_text)
        ]

        evidence["group_terms"] = group_hits[:6]
        evidence["national_terms"] = national_hits[:4]
        evidence["scope_terms"] = scope_hits[:4]
        evidence["negative_terms"] = negative_hits[:4]
        evidence["governance_terms"] = governance_hits[:5]
        evidence["public_facility_terms"] = public_facility_hits[:5]
        evidence["infrastructure_terms"] = infrastructure_hits[:6]
        evidence["private_dispute_terms"] = private_dispute_hits[:5]
        evidence["private_patterns"] = private_pattern_hits[:4]
        evidence["implied_public_patterns"] = implied_public_hits[:4]
        evidence["domain_hint_candidates"] = [item["name"] for item in domain_hint_candidates[:4]]
        evidence["semantic_object_slots"] = semantic_slots["object_slots"][:4]
        evidence["semantic_consequence_slots"] = semantic_slots["consequence_slots"][:4]
        evidence["semantic_governance_terms"] = semantic_slots["governance_terms"][:4]

        complainant_count = self._extract_complainant_count(complaint_text)
        if complainant_count:
            evidence["complainant_count"] = complainant_count

        if "长期" in complaint_text or "多年" in complaint_text or "持续" in complaint_text:
            evidence["duration_signal"] = True
        if duplicate_count >= 2 or "反复投诉" in complaint_text or "多次反映" in complaint_text:
            evidence["frequency_signal"] = True

        public_signal_count = 0
        private_signal_count = 0

        if category == "公益诉讼":
            score += 0.18
            reasons.append("主分类命中公益诉讼场景")
        if category == "公益诉讼" and (governance_hits or public_facility_hits or implied_public_hits or domain_hint_candidates):
            score += 0.08
            public_signal_count += 1
            reasons.append("主分类同时伴随较强公共利益场景信号")
        if has_location:
            score += 0.06
            reasons.append("识别到具体点位，具备外溢治理分析基础")
        if duplicate_count >= 3:
            score += 0.1
            reasons.append(f"同事项重复投诉达到 {duplicate_count} 次")
        elif duplicate_count == 2:
            score += 0.05
            reasons.append("存在重复投诉迹象")
        if positive_hits:
            score += min(0.18, 0.04 * len(positive_hits))
            public_signal_count += 1
            reasons.append(f"文本包含公共利益信号：{'、'.join(positive_hits[:4])}")
        if group_hits:
            score += min(0.14, 0.04 * len(group_hits))
            public_signal_count += 1
            reasons.append(f"涉及群体性对象：{'、'.join(group_hits[:4])}")
        if national_hits:
            score += min(0.18, 0.06 * len(national_hits))
            public_signal_count += 1
            reasons.append(f"涉及国家或社会公共利益：{'、'.join(national_hits[:3])}")
        if scope_hits:
            score += min(0.14, 0.05 * len(scope_hits))
            public_signal_count += 1
            reasons.append(f"波及范围呈区域化特征：{'、'.join(scope_hits[:3])}")
        if governance_hits:
            score += min(0.16, 0.05 * len(governance_hits))
            public_signal_count += 1
            reasons.append(f"出现监管履职或整改语义：{'、'.join(governance_hits[:3])}")
        if public_facility_hits:
            score += min(0.12, 0.04 * len(public_facility_hits))
            public_signal_count += 1
            reasons.append(f"指向公共设施或公共场景：{'、'.join(public_facility_hits[:3])}")
        if infrastructure_hits:
            score += min(0.12, 0.03 * len(infrastructure_hits))
            public_signal_count += 1
            reasons.append(f"涉及基础公共服务或公共基础设施：{'、'.join(infrastructure_hits[:3])}")
        if implied_public_hits:
            score += min(0.18, 0.08 * len(implied_public_hits))
            public_signal_count += 1
            reasons.append(f"个人表述中识别出隐含公益属性：{'、'.join(implied_public_hits[:2])}")
        if semantic_slots["object_slots"] and semantic_slots["consequence_slots"]:
            score += min(0.16, 0.05 * len(semantic_slots["object_slots"]) + 0.04 * len(semantic_slots["consequence_slots"]))
            public_signal_count += 1
            reasons.append(
                f"识别出问题客体与风险后果的组合语义：{'、'.join(semantic_slots['object_slots'][:2])} / {'、'.join(semantic_slots['consequence_slots'][:2])}"
            )
        if semantic_slots["governance_terms"] and (semantic_slots["object_slots"] or domain_hint_candidates):
            score += min(0.12, 0.04 * len(semantic_slots["governance_terms"]))
            public_signal_count += 1
            reasons.append(f"识别出治理动作语义：{'、'.join(semantic_slots['governance_terms'][:3])}")
        if domain_hint_candidates:
            score += min(0.2, 0.08 + len(domain_hint_candidates) * 0.03)
            public_signal_count += 1
            reasons.append(
                f"文本具备较强公益领域信号：{'、'.join(item['name'] for item in domain_hint_candidates[:3])}"
            )
        if evidence["duration_signal"]:
            score += 0.05
            public_signal_count += 1
            reasons.append("问题具有持续存在特征")
        if evidence["frequency_signal"]:
            score += 0.05
            public_signal_count += 1
            reasons.append("问题具有重复反映特征")
        if complainant_count >= 5:
            score += 0.08
            public_signal_count += 1
            reasons.append(f"明确提及涉事群体规模约 {complainant_count} 人")
        strong_public_context = bool(
            domain_hint_candidates or implied_public_hits or governance_hits or public_facility_hits or infrastructure_hits
        )
        if negative_hits:
            negative_penalty = min(0.2, 0.06 * len(negative_hits))
            if strong_public_context:
                negative_penalty *= 0.45
            score -= negative_penalty
            private_signal_count += 1
            reasons.append(f"文本包含明显个人利益表述：{'、'.join(negative_hits[:4])}")
        if private_dispute_hits:
            private_penalty = min(0.16, 0.05 * len(private_dispute_hits))
            if strong_public_context and (governance_hits or implied_public_hits or domain_hint_candidates):
                private_penalty *= 0.55
            score -= private_penalty
            private_signal_count += 1
            reasons.append(f"文本更接近个体纠纷诉求：{'、'.join(private_dispute_hits[:4])}")
        if private_pattern_hits:
            pattern_penalty = min(0.14, 0.05 * len(private_pattern_hits))
            if strong_public_context:
                pattern_penalty *= 0.6
            score -= pattern_penalty
            private_signal_count += 1
            reasons.append("存在明显个人维权或赔偿表达")
        if public_signal_count >= 3 and private_signal_count == 0:
            score += 0.08
            reasons.append("已形成较完整的公共利益受损语义链条")
        if public_signal_count >= 2 and strong_public_context and private_signal_count <= 1:
            score += 0.06
            reasons.append("虽含个人表述，但整体更符合公共利益受损场景")
        if private_signal_count >= 2 and public_signal_count <= 1:
            score -= 0.08
            reasons.append("个体利益表达明显强于公共利益信号")
        if domain_matches and (domain_decision or {}).get("primary_domain"):
            reasons.append(f"公益领域候选：{'、'.join(item['domain'] for item in domain_matches[:3])}")

        normalized_score = round(max(0.0, min(score, 0.99)), 4)
        direct_rule = self._resolve_direct_public_private(
            category=category,
            group_hits=group_hits,
            national_hits=national_hits,
            scope_hits=scope_hits,
            governance_hits=governance_hits,
            public_facility_hits=public_facility_hits,
            infrastructure_hits=infrastructure_hits,
            implied_public_hits=implied_public_hits,
            domain_hint_candidates=domain_hint_candidates,
            negative_hits=negative_hits,
            private_dispute_hits=private_dispute_hits,
            private_pattern_hits=private_pattern_hits,
            strong_public_term_hits=strong_public_term_hits,
            strong_private_term_hits=strong_private_term_hits,
            strong_public_pattern_hits=strong_public_pattern_hits,
            strong_private_pattern_hits=strong_private_pattern_hits,
            duplicate_count=duplicate_count,
        )
        evidence["direct_rule_level"] = direct_rule["level"]
        evidence["direct_rule_reason"] = direct_rule["reason"]

        if direct_rule["level"] == "公益":
            normalized_score = max(normalized_score, 0.58)
            reasons.append(direct_rule["reason"])
        elif direct_rule["level"] == "私益":
            normalized_score = min(normalized_score, 0.12)
            reasons.append(direct_rule["reason"])

        if normalized_score >= 0.46:
            level = "公益"
        elif normalized_score <= 0.16:
            level = "私益"
        else:
            borderline_resolution = self._resolve_borderline_public_private(
                public_signal_count=public_signal_count,
                private_signal_count=private_signal_count,
                strong_public_context=strong_public_context,
                implied_public_hits=implied_public_hits,
                domain_hint_candidates=domain_hint_candidates,
                governance_hits=governance_hits,
                public_facility_hits=public_facility_hits,
                infrastructure_hits=infrastructure_hits,
                group_hits=group_hits,
                scope_hits=scope_hits,
                private_dispute_hits=private_dispute_hits,
                private_pattern_hits=private_pattern_hits,
                negative_hits=negative_hits,
                strong_public_pattern_hits=strong_public_pattern_hits,
                strong_private_pattern_hits=strong_private_pattern_hits,
            )
            evidence["borderline_resolution"] = borderline_resolution["reason"]
            if borderline_resolution["level"] == "公益":
                level = "公益"
                normalized_score = max(normalized_score, 0.47)
                reasons.append(borderline_resolution["reason"])
            elif borderline_resolution["level"] == "私益":
                level = "私益"
                normalized_score = min(normalized_score, 0.15)
                reasons.append(borderline_resolution["reason"])
            else:
                level = "待复核"
        return {
            "level": level,
            "score": normalized_score,
            "reasons": reasons[:6] or ["当前未形成稳定的公益属性判断，建议人工复核。"],
            "evidence": evidence,
        }

    @staticmethod
    def _collect_unique_hits(complaint_text: str, terms: tuple[str, ...]) -> list[str]:
        hits: list[str] = []
        for term in terms:
            if term and term in complaint_text and term not in hits:
                hits.append(term)
        return hits

    @staticmethod
    def _collect_pattern_hits(complaint_text: str, patterns: tuple[tuple[str, str], ...]) -> list[str]:
        hits: list[str] = []
        for label, pattern in patterns:
            if label and re.search(pattern, complaint_text) and label not in hits:
                hits.append(label)
        return hits

    @staticmethod
    def _extract_semantic_text(complaint_text: str) -> str:
        if not complaint_text:
            return ""
        text = complaint_text
        main_match = re.search(r"主要内容[:：]\s*(.+)", text, re.S)
        if main_match:
            text = main_match.group(1)
        text = re.sub(
            r"(?:标题|工单类型|问题分类|工单性质|标签|企业名称|成案领域|是否解决|是否满意|受理编号|联系人|联系电话)[:：][^\n]{0,80}",
            " ",
            text,
        )
        text = re.sub(r"\s+", " ", text).strip()
        return text or complaint_text

    @staticmethod
    def _extract_domain_hint_text(complaint_text: str) -> str:
        if not complaint_text:
            return ""
        parts: list[str] = []
        for field in ("标题", "问题分类"):
            for match in re.finditer(rf"{field}[:：]\s*([^\n]+)", complaint_text):
                value = match.group(1).strip()
                if value:
                    parts.append(value)
        return " ".join(parts)

    @staticmethod
    def _extract_semantic_slots(complaint_text: str) -> dict[str, list[str]]:
        return {
            "object_slots": FeatureService._collect_slot_hits(complaint_text, SEMANTIC_OBJECT_SLOTS),
            "consequence_slots": FeatureService._collect_slot_hits(complaint_text, SEMANTIC_CONSEQUENCE_SLOTS),
            "governance_terms": FeatureService._collect_unique_hits(complaint_text, SEMANTIC_GOVERNANCE_TERMS),
        }

    @staticmethod
    def _collect_slot_hits(complaint_text: str, slot_map: dict[str, tuple[str, ...]]) -> list[str]:
        hits: list[str] = []
        lowered_text = (complaint_text or "").lower()
        for label, terms in slot_map.items():
            if any(term and term.lower() in lowered_text for term in terms):
                hits.append(label)
        return hits

    @staticmethod
    def _resolve_direct_public_private(
        *,
        category: str,
        group_hits: list[str],
        national_hits: list[str],
        scope_hits: list[str],
        governance_hits: list[str],
        public_facility_hits: list[str],
        infrastructure_hits: list[str],
        implied_public_hits: list[str],
        domain_hint_candidates: list[dict],
        negative_hits: list[str],
        private_dispute_hits: list[str],
        private_pattern_hits: list[str],
        strong_public_term_hits: list[str],
        strong_private_term_hits: list[str],
        strong_public_pattern_hits: list[str],
        strong_private_pattern_hits: list[str],
        duplicate_count: int,
    ) -> dict:
        strong_public_signal_count = sum(
            1
            for group in (
                group_hits,
                national_hits,
                scope_hits,
                governance_hits,
                public_facility_hits,
                infrastructure_hits,
                implied_public_hits,
                domain_hint_candidates,
                strong_public_term_hits,
                strong_public_pattern_hits,
            )
            if group
        )
        strong_private_signal_count = sum(
            1
            for group in (
                negative_hits,
                private_dispute_hits,
                private_pattern_hits,
                strong_private_term_hits,
                strong_private_pattern_hits,
            )
            if group
        )

        if (
            strong_public_signal_count >= 3
            and (governance_hits or public_facility_hits or implied_public_hits or domain_hint_candidates)
        ) or (
            category == "公益诉讼"
            and (strong_public_pattern_hits or strong_public_term_hits)
            and (duplicate_count >= 2 or group_hits or scope_hits)
        ):
            return {
                "level": "公益",
                "reason": "强规则直判为公益：文本已形成明确的公共利益受损与治理失灵组合信号。",
            }

        if (
            strong_private_signal_count >= 2
            and not (governance_hits or public_facility_hits or implied_public_hits or domain_hint_candidates)
        ) or (
            strong_private_pattern_hits and not strong_public_pattern_hits and not national_hits and not scope_hits
        ):
            return {
                "level": "私益",
                "reason": "强规则直判为私益：文本主要体现单人单户的赔偿、退款或合同纠纷诉求。",
            }

        return {"level": "", "reason": ""}

    @staticmethod
    def _resolve_borderline_public_private(
        *,
        public_signal_count: int,
        private_signal_count: int,
        strong_public_context: bool,
        implied_public_hits: list[str],
        domain_hint_candidates: list[dict],
        governance_hits: list[str],
        public_facility_hits: list[str],
        infrastructure_hits: list[str],
        group_hits: list[str],
        scope_hits: list[str],
        private_dispute_hits: list[str],
        private_pattern_hits: list[str],
        negative_hits: list[str],
        strong_public_pattern_hits: list[str],
        strong_private_pattern_hits: list[str],
    ) -> dict:
        has_governance_anchor = bool(governance_hits)
        has_public_facility_anchor = bool(public_facility_hits or infrastructure_hits)
        has_domain_anchor = bool(domain_hint_candidates)
        has_real_public_anchor = has_governance_anchor or has_public_facility_anchor or has_domain_anchor

        if (
            strong_public_context
            and has_real_public_anchor
            and public_signal_count >= (2 if has_domain_anchor else 3)
            and private_signal_count <= 1
            and (
                (has_governance_anchor and (group_hits or scope_hits or implied_public_hits or strong_public_pattern_hits))
                or (has_public_facility_anchor and (group_hits or scope_hits or implied_public_hits or strong_public_pattern_hits))
                or (
                    has_domain_anchor
                    and (
                        governance_hits
                        or public_facility_hits
                        or infrastructure_hits
                        or (implied_public_hits and (group_hits or scope_hits))
                    )
                )
            )
        ):
            return {
                "level": "公益",
                "reason": "边界样本二次裁决为公益：已命中真实治理语义、公共设施语义或稳定领域信号，受损客体更偏向公共利益。",
            }

        if (
            private_signal_count >= 2
            and public_signal_count <= 1
            and (private_dispute_hits or private_pattern_hits or strong_private_pattern_hits or negative_hits)
            and not (group_hits or scope_hits or governance_hits or domain_hint_candidates)
        ):
            return {
                "level": "私益",
                "reason": "边界样本二次裁决为私益：文本核心仍是单一主体的交易、赔偿或合同争议。",
            }

        return {"level": "", "reason": ""}

    @staticmethod
    def _build_other_domain_decision(reason: str) -> dict:
        return {
            "primary_domain": "其他",
            "primary_code": "OTHER",
            "confidence": 0.35,
            "candidates": [
                {
                    "code": "OTHER",
                    "name": "其他",
                    "parent_category": "公益诉讼法定领域",
                    "score": 0.35,
                    "matched_terms": [],
                    "signal_summary": {},
                    "typical_regulators": [],
                }
            ],
            "conflict_flags": [reason],
            "domain_tags": [],
        }

    @staticmethod
    def empty_legal_domain_decision() -> dict:
        return {
            "primary_domain": "",
            "primary_code": "",
            "confidence": 0.0,
            "candidates": [],
            "conflict_flags": [],
            "domain_tags": [],
        }

    @staticmethod
    def _extract_complainant_count(complaint_text: str) -> int:
        patterns = (
            r"(\d+)\s*(?:名|位)?(?:工人|工友|员工|农民工|学生|居民|住户|商户|家长|村民|租户)",
            r"(?:共|约|涉)\s*(\d+)\s*(?:人|名)",
            r"(\d+)\s*多(?:人|名)",
            r"(上百|数百|几十|数十|多名|多位|多人|众多)\s*(?:居民|住户|业主|租户|商户|群众|市民|村民|家长|学生)",
        )
        max_count = 0
        for pattern in patterns:
            for match in re.finditer(pattern, complaint_text):
                raw_value = match.group(1)
                try:
                    count = int(raw_value)
                except (TypeError, ValueError):
                    count = {
                        "多名": 3,
                        "多位": 3,
                        "多人": 3,
                        "众多": 8,
                        "数十": 30,
                        "几十": 30,
                        "数百": 100,
                        "上百": 100,
                    }.get(raw_value, 0)
                if count > max_count:
                    max_count = count
        return max_count
