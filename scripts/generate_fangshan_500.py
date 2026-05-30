# -*- coding: utf-8 -*-
"""Generate synthetic hotline-style records (Fangshan), batch 1 or batch 2 with higher diversity."""
import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "data" / "samples"

STREETS = [
    "城关街道", "拱辰街道", "西潞街道", "新镇街道", "向阳街道", "东风街道",
    "迎风街道", "星城街道", "长阳镇", "阎村镇", "窦店镇", "韩村河镇",
    "琉璃河镇", "周口店镇", "大石窝镇", "张坊镇", "十渡镇", "河北镇",
    "青龙湖镇", "石楼镇", "良乡镇", "佛子庄乡", "霞云岭乡", "史家营乡",
    "蒲洼乡", "大安山乡", "南窖乡",
]

STREET_POI = {
    "长阳镇": ["长阳半岛", "京投万科金域广场", "篱笆房地铁站周边", "长阳体育公园周边"],
    "拱辰街道": ["龙湖北京房山天街", "良乡大学城片区", "昊天大街沿线"],
    "西潞街道": ["西潞公园", "北亚骨科医院周边", "苏庄地铁站周边"],
    "城关街道": ["房山城关商业街", "燕房线城关站周边", "房山汽车站周边"],
    "阎村镇": ["阎村地铁站周边", "阎村产业园", "大紫草坞村周边"],
    "窦店镇": ["窦店物流园周边", "窦店大集", "京港澳窦店出口"],
    "周口店镇": ["周口店遗址博物馆周边", "周口店中心小学周边"],
    "十渡镇": ["十渡景区入口沿线", "十渡拒马河畔"],
    "河北镇": ["河北镇矿区道路", "108国道河北镇段"],
    "青龙湖镇": ["青龙湖环湖路", "青龙湖主景区"],
    "琉璃河镇": ["京深路琉璃河段", "琉璃河湿地公园"],
    "韩村河镇": ["韩村河大集", "韩村河西周各庄"],
    "石楼镇": ["石楼中学周边", "石楼镇政府周边"],
    "良乡镇": ["良乡镇政府周边", "良乡火车站周边"],
    "佛子庄乡": ["佛子庄乡主街", "红煤厂路口"],
    "霞云岭乡": ["堂上村周边", "霞云岭国家森林公园入口"],
}

GENERIC_LOCS = [
    "某小区及周边", "某商圈地下停车场", "某农贸市场", "某学校门口", "某地铁站口",
    "某医院西门", "某路口人行横道", "某公园公厕", "某村主街", "某产业园门口",
    "某写字楼楼道", "某餐馆门前区域", "某回迁楼院", "某村健身广场", "某河道边坡",
    "某公交场站", "某加油站旁", "某施工围挡外", "某快递驿站门口",
]

COMMUNITIES = [
    "某村", "某某社区", "某居委会", "不详", "某小区业委会", "某村党支部",
]

ENTERPRISES = [
    "北京某餐饮管理有限公司", "北京某健身休闲有限公司", "某建筑公司", "某物业公司",
    "北京某商贸有限公司", "某装饰工程有限公司", "北京某工程有限公司", "某劳务公司",
    "北京某科技有限公司", "某劳务派遣公司", "某连锁超市房山店", "",
    "",
]

PROBLEM_PATHS = [
    ("科体文宣", "文化", "文物保护"),
    ("科体文宣", "体育", "健身场所管理"),
    ("城市管理", "市容环境", "占道经营"),
    ("城市管理", "市政设施", "道路破损"),
    ("住房城乡建设", "物业管理", "电梯故障"),
    ("住房城乡建设", "物业管理", "停车管理"),
    ("市场管理", "单用途预付卡", "游泳卡"),
    ("市场管理", "单用途预付卡", "健身卡、瑜伽卡、私教卡"),
    ("市场管理", "食品安全", "餐饮卫生"),
    ("交通运输", "道路运输", "非法营运"),
    ("生态环境", "噪声", "施工噪声"),
    ("生态环境", "大气污染", "扬尘"),
    ("劳动和社会保障", "拖欠工资", "工程建设领域"),
    ("劳动和社会保障", "社会保险", "参保缴费"),
    ("教育", "校外培训", "预收费纠纷"),
    ("医疗卫生", "医疗服务", "挂号与退费"),
    ("民政", "养老服务", "机构服务"),
    ("农业农村", "农村道路", "路灯与排水"),
    ("公共安全", "消防安全", "通道占用"),
]

# Extra categories for batch 2 (more diversity)
PROBLEM_PATHS_EXTRA = [
    ("水务", "供排水", "停水与水质"),
    ("园林绿化", "公园管理", "设施损坏"),
    ("城市管理", "市容环境", "垃圾清运不及时"),
    ("住房城乡建设", "房屋质量", "渗漏与开裂"),
    ("市场监管", "价格监管", "明码标价"),
    ("市场管理", "消费纠纷", "退换货争议"),
    ("教育", "入学与划片", "学位咨询"),
    ("医疗卫生", "医保报销", "异地就医备案"),
    ("民政", "社会救助", "低保咨询"),
    ("交通运输", "公共交通", "公交线路优化"),
    ("生态环境", "噪声", "邻里噪声"),
    ("城市管理", "违法建设", "疑似违建"),
    ("公共安全", "治安", "夜间扰民"),
    ("通信管理", "通信设施", "基站与信号"),
    ("退役军人事务", "优抚安置", "政策咨询"),
]

TAG_POOLS = [
    ["多样性", "七有五性"],
    ["控烟"],
    ["营商环境"],
    ["接诉即办"],
    [],
    ["七有五性"],
    ["每月一题"],
]

NATURE = ["主办", "协办", "转办"]
SOLVED = ["解决", "未解决", "部分解决"]
SATISFIED = ["满意", "基本满意", "不满意", "未评价"]
STATUS_WEIGHTS = [("", 0.2), ("回复完成", 0.45), ("办理中", 0.2), ("已转派", 0.15)]

SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜")
GIVEN = [
    "伟", "芳", "娜", "敏", "静", "强", "磊", "军", "洋", "勇", "艳", "杰", "娟", "涛", "明",
]


def weighted_choice(pairs):
    r = random.random()
    acc = 0.0
    for val, p in pairs:
        acc += p
        if r <= acc:
            return val
    return pairs[-1][0]


def rand_id(i: int, id_offset: int) -> str:
    base = datetime(2024, 1, 1) + timedelta(days=random.randint(0, 480))
    suf = f"{(id_offset + i) % 1000000:06d}"
    return f"热线-{base.strftime('%y%m%d')}-{suf}"


def mask_phone() -> str:
    prefixes = [
        "130", "131", "132", "133", "135", "136", "137", "138", "139",
        "150", "151", "152", "155", "156", "158", "159", "166", "176",
        "182", "185", "186", "188", "198",
    ]
    return f"{random.choice(prefixes)}××××"


def rand_time() -> str:
    t = datetime(2024, 1, 1) + timedelta(
        days=random.randint(0, 500),
        hours=random.randint(8, 20),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return t.strftime("%Y-%m-%d %H:%M:%S")


def build_problem_class(a: str, b: str, c: str) -> str:
    return f"{a}->{b}->{c}"


def pick_location(street: str) -> str:
    if street in STREET_POI and random.random() < 0.55:
        return random.choice(STREET_POI[street])
    return random.choice(GENERIC_LOCS)


def _loc_phrase(loc: str) -> str:
    if loc.endswith(("周边", "沿线", "片区", "入口")):
        return loc
    return f"{loc}附近"


def random_caller_name() -> str:
    return random.choice(SURNAMES) + random.choice(GIVEN)


def main_text(street: str, loc: str, path: tuple, extended: bool) -> str:
    _, b, c = path
    near = _loc_phrase(loc)
    templates = [
        (
            f"市民反映，房山区{street}{near}存在{c}相关问题：一是现场秩序较乱，影响周边居民正常生活；"
            f"二是希望相关部门现场核查并督促整改；三是请承办单位电话告知处理结果。来电号码为本人联系方式。"
        ),
        (
            f"来电人表示，其在房山区{street}辖区{near}发现{b}方面{c}情况，已多次与现场人员沟通未果，"
            f"现通过热线反映，请属地联合行业主管部门依法处理，并尽快反馈。"
        ),
        (
            f"市民称，房山区{street}{near}近期出现与{c}相关的投诉集中情况，涉及群众出行与安全，"
            f"恳请加强巡查与执法，建立长效机制，并及时回复办理情况。"
        ),
        (
            f"诉求人反映，房山区{street}范围内{loc}涉及{c}问题，希望相关部门核实责任主体，依法依规处理，"
            f"并对同类问题开展排查，避免反弹。"
        ),
    ]
    if extended:
        templates.extend(
            [
                (
                    f"来电人称其在房山区{street}居住/工作，{near}持续出现{c}情况，已拍照留存，"
                    f"希望职能部门限期核查并书面告知处理进展。"
                ),
                (
                    f"市民通过热线反映：房山区{street}{loc}一带{b}管理不到位，导致{c}问题反复出现，"
                    f"要求开展联合执法并建立回头看机制。"
                ),
                (
                    f"诉求人陈述，房山区{street}{near}在雨天/夜间问题更明显，涉及{c}，"
                    f"请协调排水、城管或行业主管单位现场处置。"
                ),
                (
                    f"市民建议：房山区{street}应加强对{near}的日常巡查，重点整治{c}，"
                    f"并将办理结果同步至社区网格群。"
                ),
            ]
        )
    return random.choice(templates)


def reply_text(street: str, path: tuple, solved: str, extended: bool) -> str:
    _, _, c = path
    if random.random() < 0.58:
        tail = (
            "目前整改措施已落实，诉求人表示知晓。"
            if solved in ("解决", "部分解决")
            else "因客观条件或证据材料不足，短期内难以完全满足诉求，已告知法律依据与后续途径，诉求人表示知晓。"
        )
        base = (
            f"工作人员联系诉求人并开展核实。经与{street}相关单位沟通，针对“{c}”问题已安排现场核查与督促整改。"
            f"{tail}"
        )
        if extended and random.random() < 0.35:
            base = (
                f"承办单位已与诉求人电话沟通并记录诉求要点，协调{street}相关科室对“{c}”事项开展现场踏勘；{tail}"
            )
        return base
    return ""


def result_text(path: tuple, extended: bool) -> str:
    if random.random() < 0.52:
        _, _, c = path
        who = random.choice(["属地", "行业主管部门", "联合工作组", "网格力量"])
        line = f"已转{who}处理，聚焦“{c}”问题开展核查与回访。"
        if extended and random.random() < 0.3:
            line = f"已录入督办台账，由{who}牵头对“{c}”问题限期处置并反馈。"
        return line
    return ""


def control_smoking_text(street: str, loc: str, extended: bool) -> str:
    # Keep 小区点位 (loc) consistent; avoid stacking loc + another full venue name
    if extended and random.random() < 0.55:
        return f"市民反映，房山区{street}{loc}有人吸烟，影响公共环境，来电反映控烟管理问题。"
    venue = random.choice(["某商场", "某写字楼", "某餐馆", "公共卫生间"])
    return f"市民反映，房山区{street}{loc}{venue}存在吸烟问题，影响公共环境，来电反映控烟管理问题。"


def enterprise_for(path: tuple) -> str:
    a, b, c = path
    if a == "劳动和社会保障" and "拖欠" in b:
        return random.choice(["某建筑公司", "北京某工程有限公司", "某劳务公司"])
    if a == "市场管理" and b == "单用途预付卡":
        return random.choice(["北京某健身休闲有限公司", "北京某体育发展有限公司", ""])
    if a == "市场管理" and "食品" in c:
        return random.choice(["北京某餐饮管理有限公司", "某餐饮门店", ""])
    if "物业" in b:
        return random.choice(["某物业公司", ""])
    return random.choice(ENTERPRISES)


def row_for_index(
    i: int,
    id_offset: int,
    paths: list,
    extended: bool,
    control_rate: float,
) -> dict:
    street = random.choice(STREETS)
    loc = pick_location(street)
    path = random.choice(paths)

    otype = "控烟" if random.random() < control_rate else random.choice(
        ["诉求", "投诉", "咨询", "求助", "建议"]
    )

    tags = random.choice(TAG_POOLS)
    tag_str = ",".join(tags) if tags else ""

    if otype == "控烟":
        title = random.choice(
            ["公共场所吸烟", "商场卫生间吸烟", "写字楼楼道吸烟", "候车区吸烟", "餐馆包间吸烟"]
        )
        main = control_smoking_text(street, loc, extended)
        caller = random.choice(["保密", random_caller_name(), random_caller_name()])
        phone = "保密" if caller == "保密" else mask_phone()
        status = weighted_choice([("", 0.35), ("回复完成", 0.45), ("办理中", 0.2)])
        solved, sat = "", ""
        result = (
            random.choice(
                [
                    "",
                    "已督促场所管理方加强巡查并张贴禁烟标识，开展控烟宣传。",
                    "已转属地卫生健康监督机构并协调加强控烟劝导与执法巡查。",
                ]
            )
            if random.random() < 0.55
            else ""
        )
        reply = (
            random.choice(
                [
                    "",
                    "工作人员已联系诉求人并告知控烟法规与投诉渠道，提醒其注意取证与现场安全。",
                    "经核实，属地已安排工作人员现场劝导并督促管理方落实控烟管理责任。",
                ]
            )
            if random.random() < 0.45
            else ""
        )
        enterprise = ""
    else:
        title_pool = [
            f"{path[2]}相关诉求",
            f"关于{street}{loc}的情况反映",
            f"请求协调处理{path[2]}问题",
            f"投诉{path[1]}领域{path[2]}事项",
        ]
        if extended:
            title_pool.extend(
                [
                    f"房山区{street}：{path[2]}问题",
                    f"请督促处理{path[2]}（{street}）",
                ]
            )
        title = random.choice(title_pool)
        main = main_text(street, loc, path, extended)
        caller = random_caller_name()
        phone = mask_phone()
        status = weighted_choice(STATUS_WEIGHTS)
        solved = random.choice(SOLVED)
        sat = random.choice(SATISFIED)
        reply = reply_text(street, path, solved, extended)
        result = result_text(path, extended)
        enterprise = enterprise_for(path)

    comm = random.choice(COMMUNITIES)
    if random.random() < 0.22:
        comm = "不详"

    jieban_time = ""
    if status == "回复完成" or (otype != "控烟" and random.random() < 0.42):
        jieban_time = rand_time()

    return {
        "工单编号": rand_id(i, id_offset),
        "工单类型": otype,
        "问题分类": "" if otype == "控烟" else build_problem_class(*path),
        "标签": tag_str,
        "标题": title,
        "主要内容": main,
        "工单状态": status,
        "来电人": caller,
        "来电人电话/账号": phone,
        "被反映区": "房山区",
        "被反映街乡镇": street,
        "办理结果": result,
        "回复内容": reply,
        "处理受理方式": random.choice(["", "电话", "现场", "系统转派", "联合办理"]),
        "办结时间": jieban_time,
        "企业名称": enterprise,
        "是否解决": solved if otype != "控烟" else "",
        "是否满意": sat if otype != "控烟" else "",
        "工单性质": random.choice(NATURE),
        "村/社区": comm,
        "小区点位": loc,
    }


def run_batch(
    count: int,
    seed: int,
    id_offset: int,
    out_prefix: str,
    extended_paths: bool,
    control_rate: float,
) -> None:
    random.seed(seed)
    paths = list(PROBLEM_PATHS)
    if extended_paths:
        paths = paths + PROBLEM_PATHS_EXTRA
    rows = [
        row_for_index(i, id_offset, paths, extended_paths, control_rate) for i in range(count)
    ]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_prefix = str(OUTPUT_DIR / Path(out_prefix).name)
    out_csv = f"{out_prefix}.csv"
    fieldnames = [
        "工单编号", "工单类型", "问题分类", "标签", "标题", "主要内容",
        "工单状态", "来电人", "来电人电话/账号", "被反映区", "被反映街乡镇",
        "办理结果", "回复内容", "处理受理方式", "办结时间", "企业名称",
        "是否解决", "是否满意", "工单性质", "村/社区", "小区点位",
    ]
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    xlsx_path = f"{out_prefix}.xlsx"
    df = pd.DataFrame(rows)
    try:
        df.to_excel(xlsx_path, index=False, engine="openpyxl")
        print(f"Wrote {len(rows)} rows to {out_csv} and {xlsx_path}")
    except PermissionError:
        alt = f"{out_prefix}_导出.xlsx"
        df.to_excel(alt, index=False, engine="openpyxl")
        print(
            f"Wrote {len(rows)} rows to {out_csv}. "
            f"Could not write {xlsx_path} (file may be open); wrote {alt} instead."
        )


def main():
    parser = argparse.ArgumentParser(description="Generate Fangshan hotline-style synthetic rows.")
    parser.add_argument(
        "--batch",
        type=int,
        choices=[1, 2],
        default=1,
        help="1: original distribution; 2: new seed, extra categories, more templates (different sample).",
    )
    parser.add_argument("--count", type=int, default=500, help="Number of rows.")
    args = parser.parse_args()

    if args.batch == 1:
        run_batch(
            count=args.count,
            seed=20260419,
            id_offset=0,
            out_prefix="供参考线索_房山500条",
            extended_paths=False,
            control_rate=0.08,
        )
    else:
        run_batch(
            count=args.count,
            seed=20260422,
            id_offset=500_000,
            out_prefix="供参考线索_房山500条_批次2",
            extended_paths=True,
            control_rate=0.06,
        )


if __name__ == "__main__":
    main()
