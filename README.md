<div align="center">

# ☀️ 小绪 · 自我观察日记

**一面有记忆的镜子** —— 通过 AI 引导式对话，让你慢慢看清自己。

[🔗 Coze 原型验证](YOUR_COZE_BOT_LINK) · [📖 产品文档](/小绪_自我观察日记_产品经理完整手册.docx)

</div>

---

## 🎯 一句话价值

> **人在脑子里想事情，是线性循环的——越想越焦虑，越焦虑越想。小绪帮你从线性循环里跳出来，用外部视角看清楚自己。**

小绪不是让你写日记的工具，而是让你通过**自然对话**自动完成情绪梳理、归因分析和自我洞察的AI助手。每次聊完带走一个洞察，六周后带走的是关于自己的完整地图。

---

## ✨ 核心亮点

| 能力 | 实现方式 |
|------|---------|
| 🗣 **AI 引导式对话** | 四步结构：共情→归因追问→挑战假设→收束洞察 |
| 📊 **结构化解构** | 每次回复自动提取 emotion_tags / attribution / insight_draft |
| 📖 **自动生成日记** | 对话结束后，AI 自动生成结构化日记（情绪+事件+归因+反思） |
| 🔍 **跨会话洞察** | 跨越多次对话识别情绪模式和归因趋势 |
| 📈 **成长周期报告** | 每 30 天自动生成一份成长总结（情绪分布+归因分布+成长时间线） |
| 👂 **双模式切换** | 探索模式（引导型） vs 倾听模式（纯陪伴），覆盖不同场景 |
| 👁 **AI 透明性** | 对话界面实时展示 AI 当前"看到"的情绪、归因和阶段 |

---

## 🏗 系统架构

```
┌─────────────┐     ┌─────────────────────────────────────────────┐
│  用户输入    │────▶│            Multi-Agent System               │
└─────────────┘     │                                             │
                    │  ┌─────────────────────────────┐            │
                    │  │   ConversationAgent          │            │
                    │  │   ├─ EmpathySkill            │            │
                    │  │   ├─ AttributionSkill        │            │
                    │  │   ├─ ChallengeSkill          │            │
                    │  │   └─ ClosureSkill            │            │
                    │  └──────────┬──────────────────┘            │
                    │             │ structured_meta (JSON)        │
                    │  ┌──────────▼──────────────────┐            │
                    │  │   MemoryAgent                │            │
                    │  │   ├─ 写入 Message → DB      │            │
                    │  │   ├─ 更新 User Profile       │            │
                    │  │   └─ 记录 AnalyticsEvent     │            │
                    │  └──────────┬──────────────────┘            │
                    │             │                               │
                    │  ┌──────────▼──────────────────┐            │
                    │  │   InsightAgent               │            │
                    │  │     跨 Session 模式识别      │            │
                    │  └──────────┬──────────────────┘            │
                    │             │                               │
                    │  ┌──────────▼──────────────────┐            │
                    │  │   DiaryAgent                 │            │
                    │  │     对话 → 结构化日记        │            │
                    │  └──────────┬──────────────────┘            │
                    └─────────────┼───────────────────────────────┘
                                  │
                    ┌─────────────▼───────────────────────────────┐
                    │              SQLite / PostgreSQL            │
                    │  User · Session · Message · Diary · Insight │
                    │  MonthlySummary · AnalyticsEvent            │
                    └─────────────────────────────────────────────┘
```

**为什么拆成多个 Agent 而不是一个单 Agent？**
- **职责分离**：每个 Agent 只做一件事，迭代互不干扰
- **可测试**：对话质量可以单独评估，不影响记忆和洞察
- **灵活扩展**：可以单独升级某个 Agent 的推理能力

---

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3 + Flask + SQLAlchemy |
| **AI** | DeepSeek (OpenAI-compatible API) + 自定义 Agent 框架 |
| **前端** | Jinja2 + Vanilla JS + Chart.js |
| **数据库** | SQLite (dev) / PostgreSQL (prod) |
| **验证** | Coze 概念验证 → 完整工程实现 |

---

## 📁 项目结构

```
self_observation/
├── agents/                  # AI Agent 层
│   ├── conversation_agent   # 主对话 Agent（两种模式）
│   ├── diary_agent          # 日记生成 Agent
│   ├── insight_agent        # 跨会话洞察 Agent
│   ├── memory_agent         # 数据存储 Agent
│   └── monthly_summary_agent# 月度总结 Agent
├── agent_framework/         # Agent 框架基础层
│   ├── base.py              # BaseAgent + BaseSkill 抽象
│   ├── orchestrator.py      # 多 Agent 编排
│   ├── registry.py          # Agent 注册中心
│   └── skills/              # 技能插件（empathy / attribution / challenge / closure）
├── models/                  # 数据模型层
│   ├── user.py              # 用户（含身份/情绪频率/归因链）
│   ├── session.py           # 对话 Session
│   ├── message.py           # 消息（含 structured_meta JSON）
│   ├── diary.py             # 自动生成的日记
│   ├── insight.py           # 跨会话洞察
│   ├── monthly_summary.py   # 30天周期报告
│   └── analytics.py         # 产品埋点
├── routes/                  # Web 路由层
│   ├── chat.py              # 对话接口
│   ├── insights.py          # 洞察仪表盘 + 模式发现
│   ├── diaries.py           # 日记+日历
│   ├── monthly.py           # 月度报告
│   ├── profile.py           # 用户设置
│   └── analytics.py         # 数据看板
├── prompts/                 # Prompt 版本管理
│   ├── conversation_exploring_v1.md
│   ├── conversation_exploring_v2.md
│   ├── conversation_listening_v1.md
│   └── CHANGELOG.md
├── tests/                   # 测试套件
│   ├── eval_set.py          # AI 评估集（8 个测试用例 + 5 个 Bad Case）
│   └── test_api.py          # API 冒烟测试
├── templates/               # Jinja2 模板
├── static/                  # CSS + JS
├── app.py                   # Flask 入口
├── config.py                # 配置
├── seed_data.py             # Demo 数据
└── .env.example             # 环境变量模板
```

---

## 🚀 快速启动

```bash
# 1. 克隆项目
cd self_observation

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env
# 打开 .env 填入你的 DeepSeek API Key

# 4. 初始化 Demo 数据
python seed_data.py

# 5. 启动开发服务器
python app.py

# 6. 访问 http://localhost:5000
```

---

## 🧪 AI 质量评估

项目包含一个完整的 AI 评估集 `tests/eval_set.py`：

- **8 个测试用例**：覆盖工作压力、学习焦虑、绝对化用语、积极情绪、模糊情绪、人际关系、安全边界、倾听模式
- **5 个 Bad Case**：记录真实踩过的坑（追问过密、共情太浅、格式失效等）及改进方案
- 每个用例定义了：期望阶段流、期望情绪标签、安全边界检查

API 冒烟测试：
```bash
python -m pytest tests/test_api.py -v
```

---

## 🔄 Prompt 迭代历程

| 版本 | 变更 | 原因 |
|------|------|------|
| v1 | 四步引导结构 + 结构化输出格式 | MVP 需要验证"引导能否帮用户归因" |
| v2 | 注入用户个人上下文（身份/情绪趋势/归因模式） | 用户反馈"每次对话都是新的"，需要延续感 |

详见 `prompts/CHANGELOG.md`

---

## 📊 产品文档

完整的产品经理工作手册（含市场分析、竞品分析、用户测试设计、PRD、原型设计）：

👉 [小绪·自我观察日记·产品经理完整手册](/小绪_自我观察日记_产品经理完整手册.docx)

---

## 🧑‍💻 关于作者

**曾梦缘** · 广外软件工程本科 · 港理工 IT 硕士

- 目标岗位：AI 产品经理
- 博客/作品集：[coming soon]

---

## 📄 许可

MIT License
