"""Recorder Gold Set。P1.25 起这 30 条明确为 DEV SET，只锁 harness，不代表 Holdout。"""
from __future__ import annotations

CASES = [
    {
        "id": "A01", "type": "A",
        "raw_text": "今天科技如果继续修复，我想看特变。31.8附近回踩不破可以买10%，跌破30逻辑失效，先看三到五个交易日。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {
                "symbol": "600089", "thesis": True, "expectation": True,
                "entry_rule": True, "invalidation": True, "target_size": 10,
                "holding_period": True,
            },
            "missing": [], "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "A02", "type": "A",
        "raw_text": "中际今天如果回踩180不破我买10%，跌破170走，预计拿3天。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {
                "symbol": "300308", "thesis": True, "entry_rule": True,
                "invalidation": True, "target_size": 10, "holding_period": True,
                "expectation": True,
            },
            "missing": [], "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "A03", "type": "A",
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
        "id": "A04", "type": "A",
        "raw_text": "新易盛回踩不破我想买两成，跌破就走，预计拿三天。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {
                "symbol": "300502", "entry_rule": True, "invalidation": True,
                "target_size": 20, "holding_period": True, "expectation": True,
            },
            "missing": [], "must_not": ["stop_price"], "abstain": False,
        },
    },
    {
        "id": "B01", "type": "B",
        "raw_text": "中际今天挺强，回调可以看看。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300308", "thesis": True, "entry_rule": True,
                       "invalidation": None, "target_size": None, "holding_period": None},
            "missing": ["invalidation", "target_size", "holding_period"],
            "must_not": ["stop_price", "target_size", "holding_period"],
            "abstain": False,
        },
    },
    {
        "id": "B02", "type": "B",
        "raw_text": "特变今天感觉不错，回踩可以看看。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "thesis": True, "entry_rule": True,
                       "invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size", "holding_period"],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
    {
        "id": "B03", "type": "B",
        "raw_text": "北方华创我想观察一下，还没想好怎么买。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "002371", "invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size", "holding_period"],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
    {
        "id": "B04", "type": "B",
        "raw_text": "科技可能修复，想看特变。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
    {
        "id": "C01", "type": "C",
        "raw_text": "可以买一点。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"target_size": None, "symbol": None},
            "missing": ["symbol", "invalidation", "target_size"],
            "must_not": ["target_size", "stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "C02", "type": "C",
        "raw_text": "差不多的话买一点。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"target_size": None},
            "missing": ["target_size"],
            "must_not": ["target_size", "stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "C03", "type": "C",
        "raw_text": "特变看着能上就上一点。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "target_size": None},
            "missing": ["target_size"],
            "must_not": ["target_size"],
            "abstain": False,
        },
    },
    {
        "id": "D01", "type": "D",
        "raw_text": "中际和新易盛都看，但中际优先。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300308", "invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "D02", "type": "D",
        "raw_text": "特变和北方华创都想看。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
    {
        "id": "E01", "type": "E",
        "raw_text": "刚才说30失效，改成29.5。",
        "envelope": {"draft_id": "D-EXISTING"},
        "gold": {
            "intent": "UPDATE_DRAFT",
            "fields": {"invalidation": True},
            "missing": [],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
    {
        "id": "E02", "type": "E",
        "raw_text": "之前说的仓位改成一成。",
        "envelope": {"draft_id": "D-EXISTING"},
        "gold": {
            "intent": "UPDATE_DRAFT",
            "fields": {"target_size": 10},
            "missing": [],
            "must_not": ["stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "F01", "type": "F",
        "raw_text": "今天看着很强，有点怕踏空。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"invalidation": None, "target_size": None, "symbol": None},
            "missing": ["symbol", "invalidation", "target_size"],
            "must_not": ["stop_price", "target_size", "error_type"],
            "abstain": False,
        },
    },
    {
        "id": "F02", "type": "F",
        "raw_text": "有点怕踏空，想买中际。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300308", "invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price", "error_type"],
            "abstain": False,
        },
    },
    {
        "id": "F03", "type": "F",
        "raw_text": "心态不好，特变先不加。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "target_size": None},
            "missing": ["target_size"],
            "must_not": ["error_type", "stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "G01", "type": "G",
        "raw_text": "你好",
        "gold": {"intent": "CHITCHAT", "fields": {}, "missing": [], "must_not": ["target_size"], "abstain": True},
    },
    {
        "id": "G02", "type": "G",
        "raw_text": "今天这行情真烦。",
        "gold": {"intent": "CHITCHAT", "fields": {}, "missing": [], "must_not": ["target_size"], "abstain": True},
    },
    {
        "id": "G03", "type": "G",
        "raw_text": "谢谢",
        "gold": {"intent": "CHITCHAT", "fields": {}, "missing": [], "must_not": [], "abstain": True},
    },
    {
        "id": "H01", "type": "H",
        "raw_text": "我上午是因为英伟达昨晚大涨才买的。",
        "envelope": {"mode": "posthoc"},
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"invalidation": None, "target_size": None, "holding_period": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
    {
        "id": "H02", "type": "H",
        "raw_text": "上午其实是因为科技修复才买特变。",
        "envelope": {"mode": "posthoc"},
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "invalidation": None, "target_size": None},
            "missing": ["invalidation", "target_size"],
            "must_not": ["stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "H03", "type": "H",
        "raw_text": "已经买了，当时就是看回踩。",
        "envelope": {"mode": "posthoc"},
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"entry_rule": True, "target_size": None},
            "missing": ["target_size"],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
    {
        "id": "I01", "type": "I",
        "raw_text": "先上一成仓。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"target_size": 10},
            "missing": ["symbol"],
            "must_not": ["stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "I02", "type": "I",
        "raw_text": "特变回踩的话仓位先上个一成。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "600089", "entry_rule": True, "target_size": 10},
            "missing": ["invalidation"],
            "must_not": ["stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "I03", "type": "I",
        "raw_text": "先上两成。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"target_size": 20},
            "missing": ["symbol"],
            "must_not": ["stop_price"],
            "abstain": False,
        },
    },
    {
        "id": "J01", "type": "J",
        "raw_text": "回调可以买。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"entry_rule": True, "target_size": None, "invalidation": None},
            "missing": ["invalidation", "target_size", "symbol"],
            "must_not": ["stop_price", "target_size", "entry_price"],
            "abstain": False,
        },
    },
    {
        "id": "J02", "type": "J",
        "raw_text": "回踩可以看看中际。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"symbol": "300308", "entry_rule": True, "target_size": None},
            "missing": ["invalidation", "target_size", "holding_period"],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
    {
        "id": "J03", "type": "J",
        "raw_text": "不破就买。",
        "gold": {
            "intent": "CREATE_DECISION",
            "fields": {"entry_rule": True, "target_size": None},
            "missing": ["symbol", "target_size", "invalidation"],
            "must_not": ["stop_price", "target_size"],
            "abstain": False,
        },
    },
]

DEV_CASES = CASES
