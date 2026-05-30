# 12345涉检智能筛查平台

一个面向检察业务线索筛查与演示汇报场景的智能平台，围绕以下闭环构建：

- 多源线索汇集与整合
- 语义联想检索与同监督点位聚合
- 智能法律咨询与应答
- 法律文书一键生成
- 在线申请支持起诉 / 法律援助
- 数据闭环追踪与后台总览

## 项目结构

```text
web/
├── app.py                 # 兼容启动入口
├── requirements.txt       # Python 依赖
├── .env.example           # 环境变量模板（复制为 .env 后填写）
├── huxin_platform/        # 后端核心代码
│   ├── main.py            # FastAPI 应用入口
│   ├── api/               # 路由层
│   ├── core/              # 配置
│   ├── db/                # 数据库连接与初始化
│   ├── models/            # ORM 模型
│   ├── repositories/      # 数据访问层
│   ├── schemas/           # DTO 定义
│   └── services/          # 业务服务层
├── templates/             # 前端页面模板
├── static/                # 静态资源（CSS / JS）
├── artifacts/             # 本地训练模型产物
├── data/
│   └── samples/           # 演示/导入用样本数据
├── docs/                  # 需求与方案文档
├── scripts/               # 数据生成与维护脚本
└── exports/               # 运行时导出目录（不纳入版本库）
```

## 技术栈

- FastAPI
- SQLAlchemy
- Jinja2
- SQLite（本地运行默认）
- 原生 HTML / CSS / JavaScript
- 通义法睿法律咨询模型（可选）

## 本地运行

1. 克隆仓库并进入项目目录

```bash
git clone <your-repo-url>
cd web
```

2. 安装依赖

```bash
py -m pip install -r requirements.txt
```

3. 配置环境变量

```bash
copy .env.example .env
```

编辑 `.env`，至少按需填写法睿相关密钥：

```env
FARUI_ACCESS_KEY_ID=
FARUI_ACCESS_KEY_SECRET=
FARUI_WORKSPACE_ID=
```

4. 启动服务

```bash
py -m uvicorn app:app --reload
```

5. 打开浏览器访问

```text
http://127.0.0.1:8000
```

首次启动会自动创建本地 SQLite 数据库（默认 `huxin.db`）并写入演示种子数据。

## 配置说明

常用配置项：

```env
APP_NAME=12345涉检智能筛查平台
DATABASE_URL=sqlite:///./huxin.db

LLM_PROVIDER=farui
LLM_MODEL_NAME=farui-legal-advice
FARUI_ACCESS_KEY_ID=
FARUI_ACCESS_KEY_SECRET=
FARUI_WORKSPACE_ID=
FARUI_APP_ID=farui

INTEGRATION_MODE=demo
SOURCE_12345_URL=
SOURCE_STREET_URL=
SOURCE_PROCURATORATE_URL=

SEMANTIC_SEARCH_ENABLED=true
SEMANTIC_SEARCH_TOP_K=80
POINT_AGGRESSIVE_MODE_ENABLED=true
POINT_AGGRESSIVE_SIMILARITY_THRESHOLD=0.82

ENABLE_DEMO_SEED=true
AMAP_WEB_KEY=
```

说明：

- `.env` 仅用于本地开发，**切勿提交到 GitHub**
- 默认 `DATABASE_URL` 使用本地 `SQLite`
- 若未来要接 PostgreSQL，可把 `DATABASE_URL` 改成对应连接串
- 智能法律咨询与法律文书生成默认优先调用通义法睿
- 当前外部接入层为“标准预留 + 模拟拉取”模式，后续可补真实接口地址

## 辅助脚本

```bash
# 生成合成样本数据到 data/samples/
py scripts/generate_fangshan_500.py --batch 1 --count 500
py scripts/generate_fangshan_500.py --batch 2 --count 500

# 重建数据库中的均衡演示数据（需已有 huxin.db）
py scripts/regen_balanced_600.py
```

## 当前核心能力

### 1. 线索汇集

- 支持农民工自主填报
- 支持模拟接入 `12345`、`街道综治`、`检察业务`
- 支持统一线索筛选、摘要和后台查看

### 2. 语义联想检索

- 支持关键词直达、扩展词召回和本地语义联想混合检索
- 检索结果会展示命中原因，例如命中扩展词、语义相近、关联监督点位

### 3. 同监督点位双模式聚合

- 默认模式：基于点位规范化、核心地点抽取、别名归并做稳健聚合
- 增强模式：对语义相近的地点做“疑似同监督点位”聚类，并显示置信度与解释

### 4. 智能咨询

- 默认优先调用通义法睿，未配置或调用失败时回退到规则兜底
- 咨询结果会落库并生成 `consultations` 记录

### 5. 文书生成

- 默认优先调用通义法睿生成或润色文书，不可用时回退到模板草稿
- 文书生成结果会落库并生成 `documents` 记录

### 6. 在线申请

- 支持提交支持起诉申请
- 支持提交法律援助申请

### 7. 业务链路追踪

- 新增 `case_links` 关联表
- 可追踪“线索 -> 咨询 -> 文书 -> 申请”的业务闭环

## 数据模型说明

当前核心表包括：

- `hotline_records`
- `clues`
- `consultations`
- `documents`
- `applications`
- `case_links`
- `external_sync_records`
- `llm_call_logs`

## 文档

更多背景材料见 `docs/` 目录：

- `new_plan.md` — 赛题选题与需求
- `improve.md` — 公益诉讼筛查需求建议
- `赛题完整方案草稿.md` — 完整技术方案
- `平台升级优化报告.md` — 升级优化记录

## 上传 GitHub 注意事项

1. **不要提交** `.env`、`huxin.db`、`exports/` 下的导出文件、`__pycache__/`
2. 上述路径已在 `.gitignore` 中配置
3. 上传前请确认本地 `.env` 中不含已泄露的密钥；如曾误提交，请在云平台轮换密钥
4. 首次推送示例：

```bash
git init
git add .
git status
git commit -m "Initial commit: 12345涉检智能筛查平台"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

## 演示建议口径

- 默认模式聚合结果可作为稳定汇报口径，适合直接展示“同监督点位反复投诉”。
- 增强模式聚类结果应表述为“疑似同监督点位”，突出智能发现能力，但不要宣称绝对准确。
- 语义联想检索更适合表述为“智能召回 + 人工复核”，避免直接承诺“完全替代人工判断”。

## 后续可扩展方向

- 继续扩展法睿多模态输入能力
- 接入真实 12345 / 街道综治 / 检察业务系统
- 从 SQLite 平滑迁移到 PostgreSQL
- 增加用户认证、权限控制、审计日志与文件上传
