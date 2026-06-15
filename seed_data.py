#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seed demo data for testing."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from models.user import User
from models.session import Session
from models.message import Message
from models.insight import Insight
from models.diary import Diary
from models.monthly_summary import MonthlySummary
from datetime import date

app = create_app()
with app.app_context():
    db.create_all()

    user = User.query.get(1)
    if not user:
        user = User(
            id=1,
            username="demo",
            settings={"mode": "exploring", "notifications": True},
            profile={
                "identity": "职场人",
                "status": "工作中",
                "industry": "互联网",
                "profession": "运营",
                "emotion_frequencies": {"焦虑": 2, "委屈": 1, "压力": 2},
                "common_attributions": ["和同事对比进度", "害怕被否定"],
                "insight_keywords": [
                    "我害怕被否定是因为我把批评等同了失败",
                    "我的焦虑主要来自比较，而不是学习本身",
                ],
                "total_sessions": 2,
            },
            cognitive_model=User.default_cognitive_model(),
        )
        user.set_password("demo123")
        from utils.experiments import assign_experiments
        user.experiments = assign_experiments(user)
        db.session.add(user)
        db.session.commit()

    existing = Session.query.filter_by(user_id=1).first()
    if not existing:
        session1 = Session(user_id=1, mode="exploring", active=False, summary={})
        db.session.add(session1)
        db.session.commit()

        session1.add_message("user", "今天被老板骂了，真的好委屈，明明不是我的错。")
        session1.add_message("assistant", "被冤枉的感觉一定很难受。你愿意多说说当时发生了什么吗？", {
            "emotion_tags": ["委屈", "愤怒"],
            "emotion_intensity": 4,
            "stage": "empathy",
            "attribution": "",
            "absolutist_detected": [],
            "insight_draft": "",
        })
        session1.add_message("user", "他在群里直接@我，说我那个报告数据有问题，但我明明是照着以前的标准做的。")
        session1.add_message("assistant", "听起来问题出在标准变了但没人通知你。你觉得你难受的是被当众批评，还是因为被冤枉？", {
            "emotion_tags": ["委屈", "困惑"],
            "emotion_intensity": 3,
            "stage": "attribution",
            "attribution": "标准变化但没被通知，加上被当众批评",
            "absolutist_detected": [],
            "insight_draft": "",
        })
        session1.add_message("user", "都有吧。我觉得他可以直接私聊我，在群里说让人很没面子。")
        session1.add_message("assistant", "我为你把今天的对话整理成了洞察：\n\n情绪: 委屈、愤怒、困惑\n归因: 标准变化未被通知 + 被当众批评\n\n看来你在意的不只是事情本身，还有被对待的方式。", {
            "emotion_tags": ["委屈", "愤怒", "困惑"],
            "emotion_intensity": 3,
            "stage": "closure",
            "attribution": "标准变化未被通知，加上被当众批评",
            "absolutist_detected": [],
            "insight_draft": "被批评的方式比批评本身更影响我——我在意的是被尊重。下次可以主动确认标准是否更新。",
        })
        session1.active = False
        db.session.commit()

        insight1 = Insight(
            user_id=1,
            session_id=session1.id,
            emotion_tags=["委屈", "愤怒"],
            attribution_chain=["标准变化未被通知", "被当众批评"],
            insight_text="从今天的对话来看，你在工作中很在意被尊重的方式。批评本身可以接受，但被当众责备让你特别难受。你发现自己在意的不是'被批评'，而是'被批评时的姿态'——这是一个重要的自我觉察。",
            pattern_ref={"session_count": 1},
        )
        db.session.add(insight1)
        db.session.commit()

        session2 = Session(user_id=1, mode="exploring", active=True, summary={})
        db.session.add(session2)
        db.session.commit()

        session2.add_message("user", "学不进去，好焦虑，感觉别人都比我进度快。")
        session2.add_message("assistant", "焦虑真的很消耗精力。你愿意和我一起回顾一下，这种焦虑是从什么时候开始明显的吗？", {
            "emotion_tags": ["焦虑", "压力"],
            "emotion_intensity": 4,
            "stage": "empathy",
            "attribution": "",
            "absolutist_detected": [],
            "insight_draft": "",
        })

        insight2 = Insight(
            user_id=1,
            session_id=session2.id,
            emotion_tags=["焦虑", "压力"],
            attribution_chain=["和同学对比进度"],
            insight_text="你的焦虑主要来自比较，而不是学习本身。你害怕被落下，但这个恐惧本身可能比实际进度慢更消耗你。",
            pattern_ref={"session_count": 2, "emotion_frequencies": {"焦虑": 2, "压力": 1}},
        )
        db.session.add(insight2)
        db.session.commit()

        profile = user.profile or {}
        profile["total_sessions"] = 2
        user.profile = profile
        db.session.commit()

        d1 = Diary(
            user_id=1, session_id=session1.id, date=date(2026, 6, 4),
            title="6月4日·被批评后的觉察",
            content="<p>今天被老板在群里批评了。一开始很委屈，觉得自己没做错什么。</p><p>和小绪聊完之后，我意识到让我难受的不是批评本身，而是被批评时的<b>方式</b>——被当众点名让我觉得很没面子。</p><p>我发现自己很在意被尊重，可能是因为我把别人的评价和我自身的价值绑在了一起。</p>",
            emotion_tags=["委屈", "愤怒", "困惑"],
            key_events=["被老板在群里当众批评"],
            user_reflections=["难受的不是批评本身，而是被对待的方式"],
            insight_ref=insight1.id,
        )
        db.session.add(d1)

        d2 = Diary(
            user_id=1, session_id=session2.id, date=date(2026, 6, 5),
            title="6月5日·学习焦虑的根源",
            content="<p>今天复习状态很差，看到别人进度比我快就很焦虑。</p><p>小绪帮我回顾之后，我发现这种焦虑不是因为我真的学不会，而是因为我在和<b>别人比较</b>。我害怕被落下，害怕落后。</p><p>但其实每个人节奏不一样——我学到的还是我的，和谁比都没意义。</p>",
            emotion_tags=["焦虑", "压力"],
            key_events=["复习时觉得别人进度更快"],
            user_reflections=["焦虑来自比较而不是学习本身"],
            insight_ref=insight2.id,
        )
        db.session.add(d2)
        db.session.commit()

        ms = MonthlySummary(
            user_id=1, period=1, period_start=date(2026, 6, 4),
            title="第1期：从情绪到觉察的开始",
            summary_text="<p>这30天你开始了自我观察的旅程。</p><p>你发现自己在工作中最在意的不是事情本身，而是<b>被对待的方式</b>。你意识到被当众批评比批评内容本身更让你难受，这意味着你非常在意尊重和价值感。</p><p>继续记录，你会越来越了解自己。</p>",
            key_discoveries=[
                "你发现自己在意的不是批评内容，而是被对待的方式",
                "你的焦虑大多来自比较，而不是能力不足",
            ],
            growth_timeline=[
                {"week": 1, "insight": "开始记录情绪，发现批评带来的委屈感很强"},
                {"week": 2, "insight": "能区分'被批评'和'被对待的方式'，归因能力提升"},
            ],
            emotion_frequencies={"委屈": 1, "愤怒": 1, "困惑": 1, "焦虑": 1, "压力": 1},
            attribution_distribution={"被当众批评": 1, "和同学对比进度": 1},
            diary_count=2, insight_count=2,
        )
        db.session.add(ms)
        db.session.commit()

        print("Seed data created: 2 sessions, 2 insights, 2 diaries, 1 monthly summary")
    else:
        print("Data already exists, skipping seed")

    print("  User:", user.username)
    print("  Sessions:", Session.query.filter_by(user_id=1).count())
    print("  Messages:", Message.query.count())
    print("  Insights:", Insight.query.filter_by(user_id=1).count())
    print("  Diaries:", Diary.query.filter_by(user_id=1).count())
    print("  MonthlySummaries:", MonthlySummary.query.filter_by(user_id=1).count())

    # Sync to vector store
    try:
        from agents.knowledge_store import KnowledgeStore
        store = KnowledgeStore(user.id)
        count = store.sync_all(user)
        print(f"  Vector store: {count} items synced")
    except Exception as e:
        print(f"  Vector store sync skipped: {e}")
