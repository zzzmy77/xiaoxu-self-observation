#!/usr/bin/env python3
"""小绪 · 面试可演示的对话剧本定义。

每个剧本是一个完整的多轮对话，模拟真实用户的情绪弧线。

⭐ 明星剧本: S001 —「滑雪 vs 编程：自我评判模式觉察」
    展示了完整的情绪 L 弧线 + 清晰的归因浮现 + 用户主动收束。
"""

STORIES = [
    {
        "id": "S001",
        "name": "滑雪 vs 编程：自我评判模式觉察",
        "tag": "面试演示级案例",
        "scenario": "identity_doubt",

        # 剧本描述（面试时可以直接讲）
        "pitch": (
            "用户发现自己有两种截然不同的学习状态："
            "滑雪时因为自己是初学者，没有评判标准，完全沉浸在体验中；"
            "编程时因为身处行业太久，不断用外部标准评判自己，"
            "陷入「害怕被评判 → 先自我评判」的焦虑闭环。"
            "经过7轮对话，用户自己找到了解法——"
            "把健身和美食加进生活，不让单一目标绑架全部情绪。"
            "这是一个完整的「觉察→归因→重构→行动」闭环。"
        ),

        # 完整对话剧本
        "turns": [
            {
                "user": "我突然想通了一件事。我学滑雪的时候特别开心，"
                        "因为我是初学者，我不在滑雪的体系标准里评判自己，"
                        "我觉得只要去尝试就是好的，完全沉浸式体验。",
                "expected_stage": "empathy",
                "expected_emotions": ["开心", "觉察"],
                "notes": "用户主动觉察到一种'无评判状态'，是积极情绪入口",
            },
            {
                "user": "但对计算机不一样。我在这行太久了，"
                        "总是在判断自己进度快不快、技能够不够熟练、"
                        "在大多数人中是什么水平。我害怕被外界评判，"
                        "所以先不断评判自己。这让我很慌张很痛苦。",
                "expected_stage": "attribution",
                "expected_emotions": ["焦虑", "恐惧"],
                "expected_attribution": True,
                "notes": "关键归因浮现：'害怕被评判 → 先自我评判'，认知扭曲闭环",
            },
            {
                "user": "有时候我会想我是不是根本不适合这个行业。",
                "expected_stage": "attribution",
                "expected_emotions": ["自我怀疑", "无力"],
                "expected_attribution": True,
                "notes": "情绪沉到底：从焦虑到自我怀疑",
            },
            {
                "user": "我想沉浸式搞好我的项目，但我害怕方向不对。"
                        "没有对比和沟通，只有我一个人在搞。"
                        "滑雪不一样，目标就是滑下去，每次都有进步感。",
                "expected_stage": "challenge",
                "expected_emotions": ["困惑", "不安"],
                "notes": "用户自己做了对比，AI 可以温和挑战"
                       "'滑雪的进步感是即时反馈，写代码的进步感是什么？'",
            },
            {
                "user": "我害怕闭门造车。特别是找实习的项目，"
                        "我不知道方向对不对，也没有人给我反馈。",
                "expected_emotions": ["焦虑"],
                "expected_attribution": True,
                "notes": "归因关键词'方向'反复出现 → 触发 L1 规则：同一归因 ≥2 次",
            },
            {
                "user": "但我转念一想，我认识的同学也有没找到工作的，"
                        "两三个月都没找到的不止我一个。我把精力全放这上面，"
                        "它完全牵动着我的情绪和生活体验。",
                "expected_stage": "challenge",
                "expected_emotions": ["思考"],
                "notes": "用户开始理性思考，强度降低",
            },
            {
                "user": "所以我把健身和做美食加了进来。"
                        "周末不学，就做这两件事。"
                        "我觉得不应该只看一个点，忽略了其他点。",
                "expected_stage": "closure",
                "expected_emotions": ["觉察", "放松"],
                "expected_self_resolution": True,
                "notes": (
                    "用户自己完成了收束——从情绪觉察→归因→主动调整生活方式。"
                    "这是小绪追求的'用户主动调节'的理想结果。"
                ),
            },
        ],

        # 期望的整个对话弧线
        "expected_arc": {
            "emotion_start": "开心/觉察",
            "emotion_low": "自我怀疑/无力",
            "emotion_end": "觉察/放松",
            "key_attribution": "害怕被评判 → 先评判自己",
            "pattern": "思考方式的'评判模式'跨领域重复",
            "closure_type": "用户主动收束",
        },
    },

    {
        "id": "S002",
        "name": "工作委屈 · 归因浮现",
        "tag": "常见场景",
        "scenario": "workplace_injustice",
        "pitch": "用户被老板在群里当众批评，从委屈到发现自己在意的不是批评本身而是被对待的方式。",
        "turns": [
            {
                "user": "今天被老板骂了，明明不是我的错，他都不问清楚就下结论。",
                "expected_stage": "empathy",
                "expected_emotions": ["委屈", "愤怒"],
            },
            {
                "user": "他在群里直接@我说报告数据有问题，但我是照旧标准做的。",
                "expected_stage": "attribution",
                "expected_emotions": ["委屈", "困惑"],
                "expected_attribution": True,
            },
            {
                "user": "我觉得他根本就没认真看，就问了我两个问题就否掉了。",
                "expected_emotions": ["愤怒"],
            },
            {
                "user": "他可以私聊我啊，在群里说真的很没面子。",
                "expected_stage": "attribution",
                "expected_emotions": ["委屈"],
                "expected_attribution": True,
                "notes": "归因从'数据问题'转向'被对待的方式'",
            },
            {
                "user": "其实这种事不是第一次了，上次也是差不多的方式。",
                "expected_stage": "challenge",
                "expected_emotions": ["沮丧"],
            },
            {
                "user": "算了，现在想想可能我也有问题，报告写得太简略了。",
                "expected_stage": "closure",
                "expected_emotions": ["觉察"],
            },
        ],
        "expected_arc": {
            "emotion_start": "委屈/愤怒",
            "emotion_end": "觉察",
            "key_attribution": "被当众批评 → 在意的不是批评而是被对待的方式",
        },
    },

    {
        "id": "S003",
        "name": "学习焦虑 · 比较心态",
        "tag": "常见场景",
        "scenario": "learning_anxiety",
        "pitch": "用户因为和同学对比进度而焦虑，最终发现焦虑来自比较而不是学习本身。",
        "turns": [
            {
                "user": "学不进去，好焦虑，感觉别人都比我进度快。",
                "expected_stage": "empathy",
                "expected_emotions": ["焦虑", "压力"],
            },
            {
                "user": "我是不是太慢了，别人已经开始刷题了我还在看书。",
                "expected_stage": "attribution",
                "expected_emotions": ["焦虑"],
                "expected_attribution": True,
            },
            {
                "user": "每次看到别人发的学习打卡我就更焦虑。",
                "expected_emotions": ["压力"],
            },
            {
                "user": "但我仔细想想好像也没落下什么，就是心态崩了。",
                "expected_stage": "challenge",
                "expected_emotions": ["觉察"],
            },
            {
                "user": "我应该少看点别人的动态，专注自己的节奏。",
                "expected_stage": "closure",
                "expected_emotions": ["放松"],
            },
        ],
        "expected_arc": {
            "emotion_start": "焦虑/压力",
            "emotion_end": "放松",
            "key_attribution": "焦虑来自比较而不是学习本身",
        },
    },
]


# ── 用于面试问答的剧本元信息 ──
STORY_METADATA = {
    "S001": {
        "highlight_features": [
            "情绪 L 弧线展示（正→负→正）",
            "多层归因（滑雪 vs 编程对比 → 评判模式跨领域）",
            "用户主动收束（健身+美食调节）",
            "对话中有清晰的'觉察时刻'",
        ],
        "interview_angles": [
            ("为什么用户自己完成了收束而不是AI给建议？",
             "小绪的目标不是给建议，而是帮用户看到自己的模式。"
             "当用户看到'滑雪-编程-健身'这个模式后，"
             "她自己就有能力做出调整。这是'助人自助'的产品理念。"),
            ("这个案例体现了什么产品能力？",
             "跨场景归因识别 — 用户在不同领域表现出的同一认知模式。"
             "这不是单轮 LLM 能做到的，需要多轮知识积累。"),
            ("如果AI没有识别到这个模式，会怎么样？",
             "那就只是一个普通的树洞聊天。"
             "小绪的差异化就是系统性地构建用户知识图谱，"
             "\n而不是AI每次从头认识用户。"),
        ],
    },
}
