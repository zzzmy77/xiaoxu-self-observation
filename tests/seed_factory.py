#!/usr/bin/env python3
"""Seed Factory — 批量生成不同数据等级的用户用于测试.

用法:
    from tests.seed_factory import SeedFactory

    factory = SeedFactory()
    user = factory.create_user_with_history("test_user", turns=30)

支持的数据等级:
    - new_user (0-4轮): 纯 DeepSeek V4 + system prompt
    - light_user (5-15轮): 身份+情绪趋势
    - medium_user (15-50轮): +日记摘要+模式
    - heavy_user (50+轮): +洞察
"""

import sys
import os
import json
import random
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import db
from models.user import User
from models.session import Session
from models.message import Message
from models.insight import Insight
from models.diary import Diary
from models.monthly_summary import MonthlySummary
from utils.experiments import assign_experiments


# ── 情绪标签池（确保数据多样性）──
EMOTION_POOL = ["焦虑", "压力", "委屈", "愤怒", "沮丧", "无力", "自我怀疑",
                "开心", "放松", "觉察", "困惑", "不安", "失落", "悲伤"]

STAGE_POOL = ["empathy", "attribution", "challenge", "closure"]

# ── 预设对话场景（每轮对话 = user + assistant pair）──
PRESET_TURNS = [
    # 场景1: 工作委屈 (6轮完整闭环)
    {
        "scenario": "workplace_injustice",
        "emotion_tags": ["委屈", "愤怒"],
        "attribution_chain": ["被冤枉", "标准变更没通知", "被当众批评"],
        "pattern_hint": "在意被尊重的方式",
        "turns": [
            ("user", "今天被老板骂了，明明不是我的错，他都不问清楚就下结论。"),
            ("user", "他在群里直接@我说报告数据有问题，但我是照旧标准做的。"),
            ("user", "我觉得他根本就没认真看，就问了我两个问题就否掉了。"),
            ("user", "他可以私聊我啊，在群里说真的很没面子。"),
            ("user", "其实这种事不是第一次了，上次也是差不多的方式。"),
            ("user", "算了，我现在想想可能我也有问题，报告写得太简略了。"),
        ],
    },
    # 场景2: 学习焦虑 (5轮)
    {
        "scenario": "learning_anxiety",
        "emotion_tags": ["焦虑", "压力"],
        "attribution_chain": ["和同学对比进度", "害怕落后", "没有正反馈"],
        "pattern_hint": "比较驱动的焦虑模式",
        "turns": [
            ("user", "学不进去，好焦虑，感觉别人都比我进度快。"),
            ("user", "我是不是太慢了，别人已经开始刷题了我还在看书。"),
            ("user", "每次看到别人发的学习打卡我就更焦虑。"),
            ("user", "但我仔细想想，我好像也没落下什么，就是心态崩了。"),
            ("user", "我应该少看点别人的动态，专注自己的节奏。"),
        ],
    },
    # 场景3: 人际关系 (5轮)
    {
        "scenario": "relationship_frustration",
        "emotion_tags": ["失落", "不安", "困惑"],
        "attribution_chain": ["不被重视", "付出不对等", "期待落差"],
        "pattern_hint": "关系中期待落差的模式",
        "turns": [
            ("user", "我闺蜜最近总是不回我消息，但她在朋友圈给别人点赞。"),
            ("user", "我感觉自己在关系中总是付出更多的那个人。"),
            ("user", "每次都是我主动找她，她很少主动找我。"),
            ("user", "我是不是太敏感了？可能她只是忙。"),
            ("user", "但我好像经常在关系里感到不被重视。"),
        ],
    },
    # 场景4: 编程 vs 滑雪 — 自我评判模式觉察 (7轮完整闭环)
    {
        "scenario": "identity_doubt",
        "emotion_tags": ["开心", "觉察", "焦虑", "自我怀疑", "放松"],
        "attribution_chain": ["害怕被评判 → 先评判自己", "评判模式跨领域重复"],
        "pattern_hint": "从无评判的沉浸到自我评判的焦虑转化",
        "turns": [
            ("user", "我想通了一件事。我学滑雪的时候特别开心，因为我是初学者，没有评判标准，我觉得只要去尝试就是好的。"),
            ("user", "但对计算机不一样，我在这行太久了，总是在判断自己进度快不快、技能够不够熟练。"),
            ("user", "我害怕被外界评判，所以先不断评判自己。这让我很慌张很痛苦，有时候觉得不适合这个行业。"),
            ("user", "我想沉浸式搞好我的项目，但我害怕方向不对，没有对比和反馈。"),
            ("user", "滑雪的目标就是滑下去，每次都有进步感。但做项目不知道该怎么判断方向对不对。"),
            ("user", "但我想了想，我同学也有两三个月没找到工作的，我不是一个人。"),
            ("user", "所以我把健身和美食加了进来，周末不学就做这两件事。不能只看一个点忽略其他点。"),
        ],
    },
    # 场景5: 工作压力 (4轮短对话)
    {
        "scenario": "work_stress",
        "emotion_tags": ["压力", "焦虑", "无力"],
        "attribution_chain": ["工作量过大", "deadline压力"],
        "pattern_hint": "工作量过载时的应对模式",
        "turns": [
            ("user", "最近工作压力特别大，感觉快撑不住了，一堆事情做不完。"),
            ("user", "每天加班到十一二点，周末也在干活。"),
            ("user", "我跟领导反映过，他说再坚持一下，但是这个状态已经持续一个月了。"),
            ("user", "我不知道还能撑多久。"),
        ],
    },
]


class SeedFactory:
    """批量生成带聊天历史的测试用户。"""

    def __init__(self, app=None):
        if app is None:
            from app import create_app
            app = create_app()
        self.app = app
        self.ctx = app.app_context()
        self.ctx.push()

    def close(self):
        self.ctx.pop()

    def create_user(self, username, password="test123", **profile_kw):
        """创建基础用户（无聊天历史）。"""
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(
                username=username,
                settings={"mode": "exploring", "notifications": True},
                profile={
                    "identity": profile_kw.get("identity", ""),
                    "status": profile_kw.get("status", ""),
                    "industry": profile_kw.get("industry", ""),
                    "profession": profile_kw.get("profession", ""),
                    "emotion_frequencies": {},
                    "common_attributions": [],
                    "insight_keywords": [],
                    "total_sessions": 0,
                },
                cognitive_model=User.default_cognitive_model(),
            )
            user.set_password(password)
            user.experiments = assign_experiments(user)
            db.session.add(user)
            db.session.commit()
        return user

    def create_user_with_history(self, username, turn_pairs=10,
                                  scenario_focus=None, password="test123"):
        """创建带历史对话的用户。

        Args:
            username: 用户名
            turn_pairs: 总对话轮数（每条消息为一轮，turn_pairs=10 意味着5轮user+5轮assistant）
            scenario_focus: 可指定重点场景（如 "identity_doubt"），重复使用该场景
            password: 登录密码
        Returns:
            (user, sessions_list) — 用户对象和所有 session 列表
        """
        user = self.create_user(username, password=password)

        # 选场景
        if scenario_focus:
            scenarios = [s for s in PRESET_TURNS if s["scenario"] == scenario_focus]
            if not scenarios:
                scenarios = PRESET_TURNS
        else:
            scenarios = PRESET_TURNS

        sessions = []
        turns_created = 0
        session_idx = 0

        while turns_created < turn_pairs:
            session = Session(
                user_id=user.id,
                mode="exploring",
                active=False,
                summary={},
                created_at=datetime.now(timezone.utc) - timedelta(days=len(sessions)),
            )
            db.session.add(session)
            db.session.commit()

            scenario = scenarios[session_idx % len(scenarios)]
            scene_turns = scenario["turns"]
            turns_this_session = min(len(scene_turns), turn_pairs - turns_created)

            session_emotions = []
            session_attributions = []

            for i in range(turns_this_session):
                turn_idx = i % len(scene_turns)
                user_text = scene_turns[turn_idx][1]

                # Assistant 回复（含结构化 meta）
                stage = self._pick_stage(i, turns_this_session)
                emo = random.choice(scenario["emotion_tags"])
                intensity = random.randint(2, 5)
                attribution = ""
                if stage == "attribution" and scenario.get("attribution_chain"):
                    a_idx = min(i, len(scenario["attribution_chain"]) - 1)
                    attribution = scenario["attribution_chain"][a_idx]

                # 构建有意义的助手回复
                asst_text = self._generate_assistant_reply(stage, emo, attribution)

                session_emotions.append(emo)
                if attribution:
                    session_attributions.append(attribution)

                # 写入消息对
                session.add_message("user", user_text)
                session.add_message("assistant", asst_text, {
                    "emotion_tags": [emo],
                    "emotion_intensity": intensity,
                    "stage": stage,
                    "attribution": attribution,
                    "absolutist_detected": [],
                    "insight_draft": "",
                })

                turns_created += 1

            db.session.commit()

            # 生成 Insight
            if session_attributions:
                insight_text = self._generate_insight(session_attributions,
                                                       session_emotions,
                                                       scenario.get("pattern_hint", ""))
            else:
                insight_text = ""

            insight = Insight(
                user_id=user.id,
                session_id=session.id,
                emotion_tags=list(set(session_emotions)),
                attribution_chain=list(set(session_attributions)),
                insight_text=insight_text,
                pattern_ref={"session_count": session_idx + 1},
                pattern_hint=scenario.get("pattern_hint", ""),
                occurrence_count=1,
            )
            db.session.add(insight)

            # 生成 Diary
            diary = Diary(
                user_id=user.id,
                session_id=session.id,
                date=(datetime.now(timezone.utc) - timedelta(days=len(sessions))).date(),
                title=f"第{session_idx+1}次对话·{scenario['scenario']}",
                content=f"<p>今天聊了{scenario['scenario']}的话题。</p>"
                        f"<p>情绪：{'、'.join(list(set(session_emotions)))}</p>"
                        f"<p>发现：{scenario.get('pattern_hint', '继续观察中')}</p>",
                emotion_tags=list(set(session_emotions)),
                key_events=[],
                user_reflections=[insight_text] if insight_text else [],
            )
            db.session.add(diary)

            db.session.commit()

            # 更新用户 profile 中的情绪频率
            # 必须深拷贝，否则 SQLAlchemy 会认为引用未变而跳过持久化
            import copy
            profile = copy.deepcopy(user.profile) or {}
            emotion_freq = profile.get("emotion_frequencies", {})
            for e in session_emotions:
                emotion_freq[e] = emotion_freq.get(e, 0) + 1
            profile["emotion_frequencies"] = emotion_freq
            profile["common_attributions"] = list(
                set(profile.get("common_attributions", []) + session_attributions)
            )
            profile["total_sessions"] = (profile.get("total_sessions", 0) + 1)
            user.profile = profile
            db.session.commit()

            sessions.append(session)
            session_idx += 1

        return user, sessions

    def create_user_for_level(self, username, level, password="test123"):
        """按数据等级创建用户。

        Args:
            level: "new" (0-4轮) | "light" (5-15轮) | "medium" (15-50轮) | "heavy" (50+轮)
        """
        level_turns = {
            "new": 2,
            "light": 10,
            "medium": 30,
            "heavy": 60,
        }
        turn_pairs = level_turns.get(level, 10)
        return self.create_user_with_history(username, turn_pairs=turn_pairs,
                                              password=password)

    def create_demo_story_user(self):
        """创建包含滑雪vs编程故事的用户——面试演示用。"""
        return self.create_user_with_history(
            "demo_story",
            turn_pairs=14,  # 7轮对话 = 7 user + 7 assistant
            scenario_focus="identity_doubt",
        )

    def _pick_stage(self, turn_idx, total_turns):
        """根据对话进度分配阶段。"""
        if turn_idx < total_turns * 0.3:
            return "empathy"
        elif turn_idx < total_turns * 0.6:
            return "attribution"
        elif turn_idx < total_turns * 0.85:
            return "challenge"
        else:
            return "closure"

    def _generate_assistant_reply(self, stage, emotion, attribution):
        """生成有意义的助手回复。"""
        replies = {
            "empathy": [
                f"听起来真的很难受。你愿意多说说这种{emotion}的感觉是从哪里来的吗？",
                f"我能感受到你的{emotion}。这样的经历一定让你很难过。",
                f"这种感受是很真实的。能和我聊聊具体发生了什么吗？",
            ],
            "attribution": [
                f"那你觉得这种{emotion}的感觉，主要是因为什么呢？",
                f"听起来{attribution}可能是关键。你觉得呢？",
                f"我听到你说{attribution}。这让你想到了什么？",
            ],
            "challenge": [
                f"我刚才注意到你提到了一个很有意思的对比。你以前有没有类似的情况？",
                f"如果你最好的朋友遇到同样的情况，你会怎么和他说？",
                f"你说的很有道理。但换个角度想想，你觉得有没有另一种可能性？",
            ],
            "closure": [
                f"今天的对话让我看到了你的觉察力。你觉得自己从这次对话中收获了什么？",
                f"听起来你已经找到了自己的答案。要不要试着把它记录下来？",
                f"感谢你和我分享这些。接下来你有什么打算吗？",
            ],
        }
        pool = replies.get(stage, replies["empathy"])
        return random.choice(pool)

    def _generate_insight(self, attributions, emotions, pattern_hint):
        """生成 Insight 文本。"""
        parts = [
            f"从今天的对话来看，我发现你",
            f"情绪上感受到了：{'、'.join(list(set(emotions)))}",
        ]
        if attributions:
            parts.append(f"你提到的核心归因包括：{'、'.join(list(set(attributions)))}")
        if pattern_hint:
            parts.append(f"这个模式似乎在提醒你：{pattern_hint}")
        return "。".join(parts) + "。"


# ── 命令行快速生成 ──
if __name__ == "__main__":
    factory = SeedFactory()
    print("Creating users at all data levels...")

    for level in ["new", "light", "medium"]:
        user, sessions = factory.create_user_for_level(f"test_{level}", level)
        msg_count = sum(len(s.get_all_messages()) for s in sessions)
        print(f"  [{level}] user={user.username}, "
              f"sessions={len(sessions)}, "
              f"total_messages={msg_count}")

    print("Done. Users created with password: test123")
    factory.close()
