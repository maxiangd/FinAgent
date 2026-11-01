"""结构化输出的小模型兼容处理：风控 decision 的同义词映射。"""

from agents.roles.risk_mgmt.risk_review_agents import _normalize_review


def test_decision_aliases_are_normalized():
    assert _normalize_review({"decision": "hold"})["decision"] == "revise"
    assert _normalize_review({"decision": "reduce"})["decision"] == "revise"
    assert _normalize_review({"decision": "buy"})["decision"] == "approve"
    assert _normalize_review({"decision": "sell"})["decision"] == "reject"


def test_valid_decisions_are_unchanged():
    for decision in ("approve", "revise", "reject"):
        assert _normalize_review({"decision": decision})["decision"] == decision


def test_unknown_decision_kept_for_validation_error():
    payload = {"decision": "maybe", "summary": "x"}
    assert _normalize_review(payload) == payload
