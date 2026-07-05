<div align="center">

# ☀️ 小绪 · 自我观察日记

**一面有记忆的镜子** —— 通过 AI 引导式对话，让你慢慢看清自己。

[📖 产品文档](/小绪_自我观察日记_产品经理完整手册.docx)

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
| 📈 **自我洞察** | 每天自动生成一份对自己思考和行为的洞察, 丰富模式识别和人格形象 |
| 👂 **双模式切换** | 探索模式（引导型） vs 倾听模式（纯陪伴），覆盖不同场景 |
| 👁 **AI 透明性** | 对话界面实时展示 AI 当前"看到"的情绪、归因和阶段 |
| 🧠 **人物认知模型** | 10维度记忆系统，每次对话都在构建关于用户的深度理解 |

---

## 🏗 系统架构

```
用户输入 → ConversationAgent（共情→归因→挑战→收束）
              ↓ structured_meta (JSON)
          MemoryAgent（更新10维认知模型 + 情绪趋势 + 核心信念）
              ↓
          UnifiedAnalysis（跨会话模式识别 + 洞察生成）
              ↓
          DiaryAgent（对话→结构化日记）
```

**为什么拆成多个 Agent？**
- **职责分离**：每个 Agent 只做一件事，迭代互不干扰
- **可测试**：对话质量可以单独评估，不影响记忆和洞察
- **灵活扩展**：可以单独升级某个 Agent 的推理能力

### 人物认知模型（10维度）

| 维度 | 内容 |
|------|------|
| 基础信息 | 年龄、职业、教育、居住 |
| 成长背景 | 童年经历、家庭关系、关键事件 |
| 人生经历时间线 | 重大事件按时间排序 |
| 核心关系网络 | 家人/伴侣/朋友的关系动态 |
| 精神发展轨迹 | 核心信念的发现→演化→松动 |
| 情绪与心理健康趋势 | 情绪频率、波动、趋势 |
| 当前生活状态 | 工作、日常、挑战、优势 |
| 人格与认知特征 | 行为模式 + 思维习惯 |
| 价值观与深层需求 | 什么对用户最重要 |
| 兴趣与关注 | 用户关心什么 |

---

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3 + Flask + SQLAlchemy |
| **AI** | DeepSeek (OpenAI-compatible API) + 自定义 Agent 框架 |
| **前端** | Jinja2 + Vanilla JS + Chart.js (Canvas) |
| **数据库** | SQLite (dev) / PostgreSQL (prod) |

---

## 📁 项目结构

```
self_observation/
├── agents/                  # AI Agent 层
│   ├── conversation_agent   # 主对话 Agent（两种模式）
│   ├── diary_agent          # 日记生成 Agent
│   ├── memory_agent         # 认知模型更新 Agent
│   ├── insight_agent        # 跨会话洞察 Agent
│   ├── unified_analysis     # 统一分析（洞察+模式库更新）
│   ├── knowledge_base       # 私人知识库（三层检索）
│   └── knowledge_store      # 向量存储（RAG）
├── agent_framework/         # Agent 框架基础层
│   ├── base.py              # BaseAgent + BaseSkill 抽象
│   ├── orchestrator.py      # 多 Agent 编排
│   └── skills/              # 技能插件
├── models/                  # 数据模型层
│   ├── user.py              # 用户（含认知模型 JSON）
│   ├── session.py           # 对话 Session
│   ├── message.py           # 消息（含 structured_meta）
│   ├── diary.py             # 日记
│   ├── insight.py           # 洞察（含演化阶段）
│   └── monthly_summary.py   # 月度报告
├── routes/                  # Web 路由
│   ├── chat.py              # 对话接口（流式 SSE）
│   ├── insights.py          # 洞察 V2（情绪云+认知模式+转变支点）
│   ├── diaries.py           # 日记+日历
│   ├── monthly.py           # 月报
│   └── auth.py              # 登录注册
├── tests/                   # 测试
│   ├── test_api.py          # API 冒烟测试（24 个）
│   ├── test_seeded_levels.py# 数据等级 + 对话质量测试（15 个）
│   ├── seed_factory.py      # 批量生成测试用户
│   ├── stories/             # 可演示的对话剧本
│   └── test_remote.py       # 远程部署测试
├── templates/               # Jinja2 模板
├── static/                  # CSS + JS
├── prompts/                 # Prompt 版本管理
├── app.py                   # Flask 入口
├── config.py                # 配置
└── seed_data.py             # Demo 数据
```

---

## 🚀 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 打开 .env 填入你的 DeepSeek API Key

# 3. 初始化 Demo 数据
python seed_data.py

# 4. 启动开发服务器
python app.py

# 5. 访问 http://localhost:5000
# 默认账号: demo / demo123
```

---

## 📊 产品文档

完整的产品经理工作手册（含市场分析、竞品分析、用户测试设计、PRD、原型设计）：

👉 [小绪·自我观察日记·产品经理完整手册](/小绪_自我观察日记_产品经理完整手册.docx)

