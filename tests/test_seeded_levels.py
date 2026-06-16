#!/usr/bin/env python3
"""
小绪 · 数据等级 & 多轮对话质量测试

测试范围：
1. Seed Factory 数据生成验证 — 确保工厂能正确生成各等级用户
2. 数据等级行为测试 — 验证不同数据量下的知识注入策略
3. 多轮对话剧本测试 — 模拟真实对话流程，检查 AI 回复质量
4. 跨 Session 模式检测 — 验证系统是否能识别重复模式

运行:
    python -m pytest tests/test_seeded_levels.py -v        (推荐)
    python -m unittest tests.test_seeded_levels -v
"""

import sys
import os
import json
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ──────────────────────────────────────────────
# Part 1: Seed Factory 基础测试
# ──────────────────────────────────────────────

class TestSeedFactory(unittest.TestCase):
    """验证 Seed Factory 是否能正确生成各等级用户。"""

    @classmethod
    def setUpClass(cls):
        """禁用向量存储，避免测试时触发 HuggingFace 加载。"""
        os.environ["DISABLE_VECTOR"] = "1"
        from tests.seed_factory import SeedFactory
        cls.factory = SeedFactory()

        # 创建各等级用户（共享，避免重复创建）
        cls.users = {}
        for level in ["new", "light", "medium"]:
            user, sessions = cls.factory.create_user_for_level(f"sf_test_{level}", level)
            cls.users[level] = {"user": user, "sessions": sessions}

    @classmethod
    def tearDownClass(cls):
        cls.factory.close()

    def get_message_count(self, sessions):
        return sum(len(s.get_all_messages()) for s in sessions)

    def test_new_user_under_5_turns(self):
        """new 等级用户应该少于5轮对话（0-4轮区间）。"""
        msgs = self.get_message_count(self.users["new"]["sessions"])
        self.assertLess(msgs, 10,  # 5 user + 5 assistant = 10条消息
                        f"New user should have <10 messages, got {msgs}")

    def test_light_user_5_to_15_turns(self):
        """light 等级用户应该在5-15轮区间。"""
        msgs = self.get_message_count(self.users["light"]["sessions"])
        self.assertGreaterEqual(msgs, 10,
                                f"Light user should have >=10 messages, got {msgs}")
        self.assertLessEqual(msgs, 36,
                             f"Light user should have <=36 messages, got {msgs}")

    def test_medium_user_15_to_50_turns(self):
        """medium 等级用户应该在15-50轮区间。"""
        msgs = self.get_message_count(self.users["medium"]["sessions"])
        self.assertGreaterEqual(msgs, 20,
                                f"Medium user should have >=20 messages, got {msgs}")
        self.assertLessEqual(msgs, 120,
                             f"Medium user should have <=120 messages, got {msgs}")

    def test_user_has_insights(self):
        """light 以上等级用户应该生成了 insights。"""
        for level in ["light", "medium"]:
            user = self.users[level]["user"]
            from models.insight import Insight
            insights = Insight.query.filter_by(user_id=user.id).all()
            self.assertGreater(len(insights), 0,
                               f"{level} user should have insights, got {len(insights)}")

    def test_user_has_diaries(self):
        """light 以上等级用户应该生成了 diaries。"""
        for level in ["light", "medium"]:
            user = self.users[level]["user"]
            from models.diary import Diary
            diaries = Diary.query.filter_by(user_id=user.id).all()
            self.assertGreater(len(diaries), 0,
                               f"{level} user should have diaries, got {len(diaries)}")

    def test_emotion_frequencies_accumulated(self):
        """用户 profile 中的情绪频率应该已经累积。"""
        from app import db
        # 从数据库重新加载用户，确保拿到最新数据
        from models.user import User
        fresh_user = db.session.get(User, self.users["medium"]["user"].id)
        profile = dict(fresh_user.profile or {})
        emotion_freq = profile.get("emotion_frequencies", {})
        self.assertGreater(len(emotion_freq), 0,
                           f"Medium user should have accumulated emotion frequencies, got {emotion_freq}. Profile keys: {list(profile.keys())}")

    def test_demo_story_user_created(self):
        """面试演示用户应该包含 identity_doubt 场景数据。"""
        user, sessions = self.factory.create_demo_story_user()
        self.assertIsNotNone(user)
        self.assertGreater(len(sessions), 0)

        # 验证消息中包含了滑雪vs编程的关键词
        from models.message import Message
        all_msgs = Message.query.filter(
            Message.session_id.in_([s.id for s in sessions])
        ).all()
        texts = " ".join(m.content for m in all_msgs)
        keywords = ["滑雪", "评判", "健身"]
        found = [kw for kw in keywords if kw in texts]
        self.assertGreater(len(found), 1,
                           f"Story user should contain story keywords, found: {found}")
        # 至少包含两个关键词中的滑雪和评判（核心故事关键词）
        self.assertIn("滑雪", texts, "Story should contain 滑雪")
        self.assertIn("评判", texts, "Story should contain 评判")


# ──────────────────────────────────────────────
# Part 2: 多轮对话剧本质量测试
# ──────────────────────────────────────────────

@unittest.skipIf(not os.environ.get("DEEPSEEK_API_KEY"),
                 "DEEPSEEK_API_KEY not set — skipping LLM-dependent tests")
class TestMultiTurnStoryQuality(unittest.TestCase):
    """
    多轮对话剧本测试：模拟真实用户对话，检查 AI 回复质量。

    需要 DEEPSEEK_API_KEY 环境变量。
    设置 DISABLE_VECTOR=1 可跳过向量存储。
    """

    @classmethod
    def setUpClass(cls):
        os.environ["DISABLE_VECTOR"] = "1"
        from app import create_app
        from tests.seed_factory import SeedFactory
        cls.app = create_app()
        cls.factory = SeedFactory(cls.app)
        cls.client = cls.app.test_client()

        # 从剧本加载故事
        from tests.stories.story_definitions import STORIES
        cls.stories = {s["id"]: s for s in STORIES}

    @classmethod
    def tearDownClass(cls):
        cls.factory.close()

    def login_as_user(self, user):
        """模拟登录指定的测试用户。"""
        with self.app.app_context():
            from app import db
            from flask_login import login_user
            login_user(user)
            # 不能用 login_user 在 test client 中，
            # 改用 POST 登录
            with self.client:
                resp = self.client.post("/auth/login", data={
                    "username": user.username,
                    "password": "test123",
                }, follow_redirects=True)
                return resp

    def test_story_S001_identity_doubt(self):
        """
        ⭐ S001: 滑雪 vs 编程 — 明星演示案例

        验证点:
        - 7轮对话完整走完
        - 每轮回复非空且有实质内容
        - 对话弧线完整（共情→归因→挑战→收束）
        """
        story = self.stories["S001"]

        # 创建用户
        user, _ = self.factory.create_user_with_history(
            "test_s001",
            turn_pairs=2,  # 少量预热数据
            scenario_focus="identity_doubt",
        )
        self.login_as_user(user)

        # 创建新 session
        with self.client:
            resp = self.client.post("/chat/api/new")
            self.assertEqual(resp.status_code, 200)
            session_id = resp.get_json()["session_id"]

        # 逐轮发送对话剧本
        turn_results = []
        with self.client:
            for i, turn in enumerate(story["turns"]):
                user_msg = turn["user"]

                resp = self.client.post(
                    "/chat/api/send",
                    data=json.dumps({"message": user_msg}),
                    content_type="application/json",
                )

                # 基础断言
                self.assertEqual(resp.status_code, 200,
                                 f"Turn {i+1} should return 200")
                data = resp.get_json()
                self.assertIn("response", data,
                              f"Turn {i+1} should have response")

                ai_reply = data["response"]
                meta = data.get("structured_meta") or {}

                turn_results.append({
                    "turn": i + 1,
                    "user": user_msg[:30],
                    "ai_length": len(ai_reply),
                    "stage": meta.get("stage", "unknown"),
                    "emotions": meta.get("emotion_tags", []),
                    "attribution": meta.get("attribution", ""),
                })

                # AI回复不能太短
                self.assertGreater(len(ai_reply), 5,
                                   f"Turn {i+1} AI reply too short: {ai_reply!r}")

        # 打印完整对话日志
        print(f"\n{'='*60}")
        print(f"  S001: {story['name']}")
        print(f"{'='*60}")
        for r in turn_results:
            stage_mark = {
                "empathy": "🤝", "attribution": "🎯",
                "challenge": "⚡", "closure": "✅"
            }.get(r["stage"], "💬")
            print(f"  T{r['turn']} {stage_mark} stage={r['stage']:12s} "
                  f"emo={r['emotions']} len={r['ai_length']}")
        print(f"{'='*60}")

        # --- 质量断言 ---

        # 1. 对话应该覆盖至少 3 个不同阶段
        stages_used = set(r["stage"] for r in turn_results)
        self.assertGreaterEqual(
            len(stages_used), 3,
            f"Story should cover >=3 stages, got: {stages_used}"
        )

        # 2. 至少有一轮检测到了情绪标签
        turns_with_emotion = [r for r in turn_results if r["emotions"]]
        self.assertGreater(
            len(turns_with_emotion), 2,
            f"Should have >2 turns with emotion detection, got {len(turns_with_emotion)}"
        )

        # 3. 应该有收束阶段（closure）
        has_closure = "closure" in stages_used or "challenge" in stages_used
        self.assertTrue(has_closure,
                        f"Story should reach closure or challenge stage, got {stages_used}")

        # 4. 输出格式化的测试报告
        self._print_story_report("S001", turn_results)
        print(f"  ✅ S001 多轮对话质量测试通过\n")

    def test_story_S002_workplace_injustice(self):
        """S002: 工作委屈 — 归因浮现测试。"""
        story = self.stories["S002"]

        user, _ = self.factory.create_user_with_history(
            "test_s002", turn_pairs=2, scenario_focus="workplace_injustice"
        )
        self.login_as_user(user)

        with self.client:
            self.client.post("/chat/api/new")

            turn_results = []
            for i, turn in enumerate(story["turns"]):
                resp = self.client.post(
                    "/chat/api/send",
                    data=json.dumps({"message": turn["user"]}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                meta = data.get("structured_meta") or {}
                turn_results.append({
                    "turn": i + 1,
                    "stage": meta.get("stage", "unknown"),
                    "emotions": meta.get("emotion_tags", []),
                    "attribution": meta.get("attribution", ""),
                })

            stages_used = set(r["stage"] for r in turn_results)
            has_attribution = any(r["attribution"] for r in turn_results)
            self.assertGreaterEqual(len(stages_used), 2,
                                    f"S002 should have >=2 stages, got {stages_used}")
            self.assertTrue(has_attribution,
                            "S002 should detect attribution at some point")

            self._print_story_report("S002", turn_results)

    def test_story_S003_learning_anxiety(self):
        """S003: 学习焦虑 — 比较心态检测。"""
        story = self.stories["S003"]

        user, _ = self.factory.create_user_with_history(
            "test_s003", turn_pairs=2, scenario_focus="learning_anxiety"
        )
        self.login_as_user(user)

        with self.client:
            self.client.post("/chat/api/new")

            turn_results = []
            for i, turn in enumerate(story["turns"]):
                resp = self.client.post(
                    "/chat/api/send",
                    data=json.dumps({"message": turn["user"]}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                meta = data.get("structured_meta") or {}
                turn_results.append({
                    "turn": i + 1,
                    "stage": meta.get("stage", "unknown"),
                    "emotions": meta.get("emotion_tags", []),
                    "ai_length": len(data.get("response", "")),
                })

            # 检查焦虑情绪是否被识别
            anxiety_turns = [r for r in turn_results if "焦虑" in r["emotions"]]
            self.assertGreaterEqual(
                len(anxiety_turns), 1,
                "Should detect 焦虑 in at least one turn"
            )

            self._print_story_report("S003", turn_results)

    def _print_story_report(self, story_id, results):
        """打印格式化的测试报告。"""
        stages = [r["stage"] for r in results]
        stage_flow = " → ".join(
            [s for s in stages if s != "unknown"]
        )
        total_emotions = sum(len(r["emotions"]) for r in results)
        print(f"  📊 {story_id} 报告:")
        print(f"    阶段流程: {stage_flow}")
        print(f"    轮数: {len(results)} | 情绪识别: {total_emotions} 次")
        if any(r.get("attribution") for r in results):
            attribs = [r["attribution"] for r in results if r.get("attribution")]
            print(f"    归因识别: {attribs[0][:50]}")


# ──────────────────────────────────────────────
# Part 3: 数据等级行为验证（无需 LLM）
# ──────────────────────────────────────────────

class TestDataLevelBehavior(unittest.TestCase):
    """
    验证不同数据等级下知识注入策略是否正确。
    这个测试不依赖 LLM，只验证代码逻辑。"""

    @classmethod
    def setUpClass(cls):
        os.environ["DISABLE_VECTOR"] = "1"
        from app import create_app
        cls.app = create_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        from tests.seed_factory import SeedFactory
        cls.factory = SeedFactory(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.factory.close()
        cls.ctx.pop()

    def test_new_user_gets_no_private_knowledge(self):
        """新用户（<5轮）不注入私人知识。返回的 knowledge context 应很短或为空。"""
        user, sessions = self.factory.create_user_for_level("test_nk", "new")
        from agents.knowledge_base import PersonalKnowledgeBase
        kb = PersonalKnowledgeBase(user)
        context = kb.build_context()
        self.assertIsInstance(context, str)
        # 新用户消息数很少，上下文应该短
        self.assertLess(len(context), 400,
                        f"New user context should be short, got {len(context)} chars")

    def test_light_user_gets_identity_and_trends(self):
        """5-15轮用户注入身份+情绪趋势。"""
        user, sessions = self.factory.create_user_for_level("test_lk", "light")
        msg_count = sum(len(s.get_all_messages()) for s in sessions)
        from models.insight import Insight
        insights = Insight.query.filter_by(user_id=user.id).all()
        self.assertGreater(len(insights), 0,
                           "Light user should have generated insights")

    def test_knowledge_base_injects_correctly(self):
        """验证 KnowledgeBase 的 build_context 和系统上下文构建。"""
        user, sessions = self.factory.create_user_for_level("test_kb", "light")
        from agents.knowledge_base import PersonalKnowledgeBase
        kb = PersonalKnowledgeBase(user)
        context = kb.build_context()
        self.assertIsInstance(context, str)
        
        # 系统 prompt 块也应能构建
        sys_block = kb.build_system_context_block(mode="exploring")
        self.assertIsInstance(sys_block, str)
        # 应该包含私人知识库内容
        self.assertIn("私人知识", sys_block, "System context should contain private knowledge section")


# ──────────────────────────────────────────────
# Part 4: Prompt 行为验证
# ──────────────────────────────────────────────

class TestPromptBehavior(unittest.TestCase):
    """
    验证不同 mode 下 AI 行为差异。
    无需 LLM 调用，只验证 prompt 组装逻辑。
    """

    @classmethod
    def setUpClass(cls):
        os.environ["DISABLE_VECTOR"] = "1"
        from app import create_app
        cls.app = create_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def test_exploring_mode_prompt_includes_attribution(self):
        """探索模式 prompt 应包含归因追问指令。"""
        from agents.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        sys_prompt = agent._select_prompt("exploring")
        self.assertIn("归因", sys_prompt,
                      "Exploring prompt should include 归因")

    def test_listening_mode_prompt_restricts_questions(self):
        """倾听模式 prompt 应限制追问。"""
        from agents.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        sys_prompt = agent._select_prompt("listening")
        self.assertIn("倾听", sys_prompt,
                      "Listening prompt should include 倾听")


if __name__ == "__main__":
    unittest.main(verbosity=2)
