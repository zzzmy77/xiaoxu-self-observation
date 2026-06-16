#!/usr/bin/env python3
"""
远程测试 — 针对 Railway 部署的小绪 API 测试。

用法:
    # 必须先设置 RAILWAY_URL（你部署的地址）
    export RAILWAY_URL=https://your-app.railway.app
    
    # 1. 种子数据同步到服务器（第1次跑）
    python tests/test_remote.py --seed light
    
    # 2. 运行远程测试
    python tests/test_remote.py
    
    # 3. 完整流程：种子 + 全部测试
    python tests/test_remote.py --seed medium
"""

import sys
import os
import json
import time
import argparse

import requests


def get_base_url():
    url = os.environ.get("RAILWAY_URL")
    if not url:
        print("❌ 请设置 RAILWAY_URL 环境变量，例如:")
        print("   export RAILWAY_URL=https://xiaoxu.up.railway.app")
        print("   或者在 Windows: set RAILWAY_URL=https://xiaoxu.up.railway.app")
        sys.exit(1)
    return url.rstrip("/")


# ──────────────────────────────────────────────
# Session 管理（requests.Session 保持 cookie）
# ──────────────────────────────────────────────

class RemoteClient:
    """封装远程 API 调用。"""

    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Xiaoxu-Remote-Test/1.0",
        })

    def get(self, path, **kwargs):
        return self.session.get(f"{self.base_url}{path}", **kwargs)

    def post(self, path, **kwargs):
        return self.session.post(f"{self.base_url}{path}", **kwargs)

    def post_json(self, path, data=None, **kwargs):
        headers = {"Content-Type": "application/json"}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        return self.session.post(
            f"{self.base_url}{path}",
            data=json.dumps(data or {}),
            headers=headers,
            **kwargs,
        )


# ──────────────────────────────────────────────
# 种子数据
# ──────────────────────────────────────────────

def seed_data(client, level="light"):
    """调用服务器 seed 端点生成测试数据。"""
    print(f"\n🌱 Seeding {level} data...")
    resp = client.post(f"/admin/seed?level={level}",
                        headers={"X-Seed-Key": "xiaoxu-dev-tool"})
    if resp.status_code == 403:
        print("   ❌ 需要 X-Seed-Key 头。如果是 debug 模式，确保 Flask 在 debug 模式下运行。")
        print(f"      响应: {resp.text}")
        return False
    elif resp.status_code != 200:
        print(f"   ❌ Seed 失败: {resp.status_code}")
        print(f"      响应: {resp.text}")
        return False

    data = resp.json()
    print(f"   ✅ {data['level']} 级数据已生成")
    stats = data["stats"]
    print(f"      会话: {stats['sessions']} | 消息: {stats['messages']}")
    print(f"      洞察: {stats['insights']} | 日记: {stats['diaries']}")
    return True


# ──────────────────────────────────────────────
# 基础连接测试
# ──────────────────────────────────────────────

def test_health(client):
    """检查服务是否在线。"""
    print("\n🏥 健康检查...")
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    data = resp.json()
    assert data.get("status") == "ok"
    print(f"   ✅ 服务在线: {data.get('app', '小绪')}")
    return True


def test_login_demo(client):
    """登录 demo 用户。"""
    print("\n🔑 登录 demo 用户...")
    resp = client.post("/auth/login", data={
        "username": "demo",
        "password": "demo123",
    })
    assert resp.status_code in (200, 302), f"Login failed: {resp.status_code}"
    print("   ✅ 登录成功")
    return True


def test_chat_page(client):
    """聊天页面可访问。"""
    print("\n💬 访问聊天页面...")
    resp = client.get("/chat/")
    assert resp.status_code == 200, f"Chat page failed: {resp.status_code}"
    # 检查页面包含关键元素
    assert "小绪" in resp.text, "Chat page missing title"
    print("   ✅ 聊天页面正常")
    return True


# ──────────────────────────────────────────────
# 单轮对话测试
# ──────────────────────────────────────────────

def test_send_message(client, message="今天心情不太好"):
    """发送一条消息并检查回复。"""
    print(f"\n📤 发送: \"{message}\"...")
    resp = client.post_json("/chat/api/send", {"message": message})
    assert resp.status_code == 200, f"Send message failed: {resp.status_code}"
    data = resp.json()
    assert "response" in data, "No response field"
    assert len(data["response"]) > 0, "Empty response"
    meta = data.get("structured_meta") or {}
    print(f"   ✅ AI 回复 ({len(data['response'])} 字符)")
    if meta.get("emotion_tags"):
        print(f"      情绪识别: {meta['emotion_tags']}")
    if meta.get("stage"):
        print(f"      阶段: {meta['stage']}")
    return data


# ──────────────────────────────────────────────
# 多轮对话剧本测试
# ──────────────────────────────────────────────

def test_multi_turn_story(client, story_id="S001"):
    """运行对话剧本，逐轮检查 AI 回复质量。"""
    from tests.stories.story_definitions import STORIES
    stories = {s["id"]: s for s in STORIES}
    story = stories.get(story_id)
    if not story:
        print(f"   ❌ 找不到剧本 {story_id}")
        return False

    print(f"\n🎭 {story['name']}")
    print(f"   {story.get('pitch', '')[:80]}...")

    # 新会话
    resp = client.post("/chat/api/new")
    assert resp.status_code == 200, f"New session failed: {resp.status_code}"

    results = []
    for i, turn in enumerate(story["turns"]):
        user_msg = turn["user"]
        print(f"\n   T{i+1} 👤 {user_msg[:40]}...")

        resp = client.post_json("/chat/api/send", {"message": user_msg})
        assert resp.status_code == 200, f"Turn {i+1} failed: {resp.status_code}"

        data = resp.json()
        meta = data.get("structured_meta") or {}
        ai_reply = data.get("response", "")

        results.append({
            "turn": i + 1,
            "ai_length": len(ai_reply),
            "stage": meta.get("stage", "unknown"),
            "emotions": meta.get("emotion_tags", []),
            "attribution": meta.get("attribution", ""),
        })

        print(f"       🤖 [{meta.get('stage','?')}] {ai_reply[:60]}...")

    # 统计
    stages = set(r["stage"] for r in results)
    emotions = sum(len(r["emotions"]) for r in results)

    print(f"\n   📊 报告:")
    print(f"      阶段流程: {' → '.join([r['stage'] for r in results if r['stage'] != 'unknown'])}")
    print(f"      轮数: {len(results)} | 情绪识别: {emotions} 次")
    if any(r.get("attribution") for r in results):
        attr = next(r["attribution"] for r in results if r.get("attribution"))
        print(f"      归因识别: {attr[:50]}")

    assert len(stages) >= 2, f"Should cover >=2 stages, got {stages}"
    print(f"\n   ✅ {story_id} 测试通过")
    return True


# ──────────────────────────────────────────────
# 页面测试
# ──────────────────────────────────────────────

def test_pages(client):
    """检查所有主要页面可访问。"""
    print("\n📄 页面访问测试...")
    pages = [
        ("聊天", "/chat/"),
        ("洞察", "/insights/"),
        ("日记", "/diaries/"),
        ("月度", "/monthly/"),
        ("个人", "/profile/"),
    ]
    for name, path in pages:
        resp = client.get(path)
        status = "✅" if resp.status_code == 200 else "❌"
        print(f"   {status} {name} ({resp.status_code})")
        assert resp.status_code == 200, f"{name} page failed: {resp.status_code}"
    return True


# ──────────────────────────────────────────────
# API 数据测试
# ──────────────────────────────────────────────

def test_insights_api(client):
    """洞察 API 返回结构化数据。"""
    print("\n📊 洞察 API...")
    resp = client.get("/insights/api/data")
    assert resp.status_code == 200
    data = resp.json()
    assert "emotion_frequencies" in data
    assert "attributions" in data
    print(f"   ✅ 情绪种类: {len(data.get('emotion_frequencies', {}))}")
    print(f"      归因数量: {len(data.get('attributions', []))}")
    print(f"      会话数: {data.get('session_count', 0)}")
    return data


def test_profile_api(client):
    """个人信息 API。"""
    print("\n👤 个人信息 API...")
    resp = client.get("/profile/api")
    assert resp.status_code == 200
    data = resp.json()
    assert "username" in data
    print(f"   ✅ 用户: {data.get('username')}")
    return data


# ──────────────────────────────────────────────
# 主动洞察推送测试
# ──────────────────────────────────────────────

def test_proactive_message(client):
    """新对话时是否触发 proactive message。"""
    print("\n🔔 主动洞察推送...")
    resp = client.get("/chat/")
    assert resp.status_code == 200
    # proactive 消息会包含在 chat 页面的 HTML 中
    has_proactive = 'proactive-msg' in resp.text or '开场白' in resp.text
    if has_proactive:
        print("   ✅ 触发了主动洞察推送")
    else:
        print("   ℹ️  未触发（数据量不够或规则未命中，正常）")
    return has_proactive


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def run_all(client):
    """按顺序执行所有测试。"""

    results = []

    def run(name, func, *args):
        try:
            func(client, *args)
            results.append((name, True, ""))
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"      ❌ 失败: {e}")

    run("健康检查", test_health)
    run("登录", test_login_demo)
    run("聊天页面", test_chat_page)
    run("页面访问", test_pages)
    run("发送消息", test_send_message, "今天心情不太好，想找人聊聊")
    run("洞察 API", test_insights_api)
    run("个人信息 API", test_profile_api)
    run("主动洞察", test_proactive_message)
    run("剧本 S001", test_multi_turn_story, "S001")
    run("剧本 S002", test_multi_turn_story, "S002")

    # 汇总
    print(f"\n{'='*50}")
    print(f"  测试汇总")
    print(f"{'='*50}")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, err in results:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if not ok and err:
            print(f"     原因: {err}")
    print(f"\n  通过: {passed}/{len(results)}")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="小绪远程测试")
    parser.add_argument("--seed", choices=["new", "light", "medium"],
                       help="先向服务器同步种子数据")
    parser.add_argument("--url", help="Railway URL (或设置 RAILWAY_URL)")
    args = parser.parse_args()

    base_url = args.url or get_base_url()
    client = RemoteClient(base_url)
    print(f"🔗 目标: {base_url}")

    # 种子数据
    if args.seed:
        if not seed_data(client, args.seed):
            sys.exit(1)

    # 跑测试
    ok = run_all(client)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
