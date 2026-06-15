"""
A/B 测试框架 — 实验分流 + 埋点辅助。

使用方式：
  1. 注册时自动分配实验组（auth.py 调 assign_experiments）
  2. Agent/路由中调 get_experiment_group() 走不同逻辑
  3. 埋点时调 annotate_properties() 自动标记分组
"""

import random

EXPERIMENTS = {
    "prompt_style": {
        "description": "Prompt 详细版 vs 精简版",
        "groups": ["control", "treatment"],
        "weights": [0.5, 0.5],
    },
    "data_level": {
        "description": "注入门槛阈值测试（保守 vs 激进）",
        "groups": ["control", "treatment"],
        "weights": [0.5, 0.5],
    },
    "kb_content": {
        "description": "注入内容组合（全量 vs 仅日记）",
        "groups": ["full", "diary_only"],
        "weights": [0.5, 0.5],
    },
}


def assign_experiments(user) -> dict:
    """为用户分配所有实验组（注册 / 首次登录时调用）。"""
    assigned = dict(user.experiments) if user.experiments else {}
    for name, config in EXPERIMENTS.items():
        if name not in assigned:
            assigned[name] = random.choices(
                config["groups"], weights=config["weights"], k=1
            )[0]
    return assigned


def get_group(user, name: str) -> str:
    """获取用户在某个实验中的分组。"""
    if not user or not user.experiments:
        return "control"
    return user.experiments.get(name, "control")


def annotate_properties(user, event_name: str = "", **kwargs) -> dict:
    """埋点时自动添加用户当前实验分组到 properties。"""
    props = dict(kwargs)
    if user and user.experiments:
        for exp_name, group in user.experiments.items():
            props[f"exp_{exp_name}"] = group
    return props
