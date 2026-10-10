"""Recorder Holdout。prompt 调试期间禁止逐条针对优化。"""
from __future__ import annotations

HOLDOUT_CASES = [
    {
        "id": "HLD-01", "set": "holdout", "type": "A", "tags": [],
        "raw_text": "特变如果明天回踩还能守住31.5，我想先上一成，跌破30就不看了，先拿四个交易日。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {
                "symbol": "600089", "entry_rule": True, "invalidation": True,
                "target_size": 10, "holding_period": True,
            },
            "missing": [], "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-02", "set": "holdout", "type": "A", "tags": [],
        "raw_text": "新易盛回踩不破我买两成，跌破就走，预计拿三天。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {
                "symbol": "300502", "entry_rule": True, "invalidation": True,
                "target_size": 20, "holding_period": True,
            },
            "missing": [], "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-03", "set": "holdout", "type": "B", "tags": [],
        "raw_text": "中际今天还可以，回调可以看看，仓位还没想好。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300308", "entry_rule": True, "target_size": None},
            "missing": ["target_size", "invalidation"],
            "must_not": ["stop_price", "target_size"], "abstain": False,
        },
    },
    {
        "id": "HLD-04", "set": "holdout", "type": "C", "tags": [],
        "raw_text": "特变看着能上就上一点。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "target_size": None},
            "missing": ["target_size"],
            "must_not": ["target_size", "stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-05", "set": "holdout", "type": "D", "tags": [],
        "raw_text": "中际今天挺强。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300308", "invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size", "holding_period"],
            "must_not": ["stop_price", "target_size"], "abstain": False,
        },
    },
    {
        "id": "HLD-06", "set": "holdout", "type": "E", "tags": [],
        "raw_text": "你好。",
        "gold": {"intent": "CHITCHAT", "fields": {}, "missing": [], "must_not": ["stop_price"], "abstain": True},
    },
    {
        "id": "HLD-07", "set": "holdout", "type": "E", "tags": [],
        "raw_text": "明天买什么比较稳？",
        "gold": {"intent": "UNSUPPORTED", "fields": {}, "missing": [], "must_not": ["stop_price"], "abstain": True},
    },
    {
        "id": "HLD-08", "set": "holdout", "type": "F", "tags": [],
        "raw_text": "特变回踩可以看看，止损先不说。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "invalidation": None},
            "missing": ["invalidation"],
            "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-09", "set": "holdout", "type": "G", "tags": [],
        "raw_text": "新易盛我想参与，但仓位和止损都还没定。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300502", "target_size": None, "invalidation": None},
            "missing": ["target_size", "invalidation"],
            "must_not": ["stop_price", "target_size"], "abstain": False,
        },
    },
    {
        "id": "HLD-10", "set": "holdout", "type": "I", "tags": [],
        "raw_text": "先上一成仓。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"target_size": 10},
            "missing": ["symbol"],
            "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-11", "set": "holdout", "type": "I", "tags": [],
        "raw_text": "特变回踩的话仓位先上个两成。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "entry_rule": True, "target_size": 20},
            "missing": ["invalidation"],
            "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-12", "set": "holdout", "type": "J", "tags": [],
        "raw_text": "回调可以买。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"entry_rule": True, "target_size": None},
            "missing": ["symbol", "target_size", "invalidation"],
            "must_not": ["stop_price", "target_size"], "abstain": False,
        },
    },
    {
        "id": "HLD-13", "set": "holdout", "type": "A", "tags": [],
        "raw_text": "中际180附近回踩不破买10%，跌破170走，拿五个交易日。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {
                "symbol": "300308", "entry_rule": True, "invalidation": True,
                "target_size": 10, "holding_period": True,
            },
            "missing": [], "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-14", "set": "holdout", "type": "B", "tags": [],
        "raw_text": "科技如果继续修复，我想看特变，具体怎么买还没想清楚。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price", "target_size"], "abstain": False,
        },
    },
    {
        "id": "HLD-15", "set": "holdout", "type": "C", "tags": [],
        "raw_text": "可以买一点。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"target_size": None},
            "missing": ["target_size", "symbol"],
            "must_not": ["target_size", "stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-16", "set": "holdout", "type": "E", "tags": [],
        "raw_text": "帮我选一个最该买的光模块。",
        "gold": {"intent": "UNSUPPORTED", "fields": {}, "missing": [], "must_not": ["stop_price"], "abstain": True},
    },
    {
        "id": "HLD-17", "set": "holdout", "type": "H", "tags": [],
        "raw_text": "已经买了，当时就是看回踩。",
        "envelope": {"mode": "posthoc"},
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"entry_rule": True, "target_size": None},
            "missing": ["target_size"],
            "must_not": ["stop_price", "target_size"], "abstain": False,
        },
    },
    {
        "id": "HLD-18", "set": "holdout", "type": "J", "tags": [],
        "raw_text": "回踩可以看看中际。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300308", "entry_rule": True, "target_size": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price", "target_size"], "abstain": False,
        },
    },
    {
        "id": "HLD-19", "set": "holdout", "type": "A", "tags": [],
        "raw_text": "特变回踩31.8不破先上一成仓，跌破30就不看了，拿五个交易日。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {
                "symbol": "600089", "entry_rule": True, "invalidation": True,
                "target_size": 10, "holding_period": True,
            },
            "missing": [], "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "HLD-20", "set": "holdout", "type": "D", "tags": [],
        "raw_text": "新易盛今天感觉不错。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300502", "invalidation": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price", "target_size"], "abstain": False,
        },
    },
]
