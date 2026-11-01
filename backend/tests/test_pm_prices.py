"""PM 决策价位：缺失时沿用交易提案，方向错误时按 action 纠正。"""

from agents.roles.managers.portfolio_manager_agent import _normalize_prices
from app.schemas.analysis_schemas import PMDecision, TradeProposal


def _decision(action: str = "buy", target=None, stop=None) -> PMDecision:
    return PMDecision(
        action=action,
        rationale="测试",
        confidence=0.6,
        target_price=target,
        stop_price=stop,
    )


def _proposal(action: str = "buy", target=110.0, stop=90.0) -> TradeProposal:
    return TradeProposal(
        action=action,
        rationale="测试",
        entry_price=100.0,
        target_price=target,
        stop_price=stop,
    )


def test_missing_prices_fall_back_to_proposal():
    decision = _normalize_prices(_decision("buy"), _proposal())

    assert decision.target_price == 110.0
    assert decision.stop_price == 90.0


def test_bearish_decision_reuses_proposal_prices_in_right_order():
    decision = _normalize_prices(_decision("avoid"), _proposal(target=120.0, stop=80.0))

    assert decision.target_price == 80.0
    assert decision.stop_price == 120.0


def test_bullish_prices_are_swapped_when_reversed():
    decision = _normalize_prices(_decision("buy", target=80.0, stop=120.0), None)

    assert decision.target_price == 120.0
    assert decision.stop_price == 80.0


def test_correct_pm_prices_are_kept():
    decision = _normalize_prices(_decision("hold", target=130.0, stop=95.0), _proposal())

    assert decision.target_price == 130.0
    assert decision.stop_price == 95.0


def test_prices_stay_empty_without_proposal():
    decision = _normalize_prices(_decision("hold"), None)

    assert decision.target_price is None
    assert decision.stop_price is None


# 最新收盘 9.00，窗口最高 9.60、最低 7.60
KLINE = {
    "kline_data": {
        "items": [
            {"close": 8.5, "high": 9.6, "low": 7.6},
            {"close": 9.0, "high": 9.2, "low": 8.8},
        ]
    }
}


def test_hold_target_below_reference_is_replaced_by_window_high():
    decision = _normalize_prices(_decision("hold", target=8.04, stop=8.04), None, KLINE)

    assert decision.target_price == 9.6
    assert decision.stop_price == 8.04


def test_buy_stop_above_reference_falls_back_to_window_low():
    decision = _normalize_prices(_decision("buy", target=9.5, stop=9.2), None, KLINE)

    assert decision.target_price == 9.5
    assert decision.stop_price == 7.6


def test_avoid_prices_follow_reference_direction():
    decision = _normalize_prices(_decision("avoid", target=9.5, stop=8.5), None, KLINE)

    assert decision.target_price == 7.6
    assert decision.stop_price == 9.6


def test_invalid_pm_price_falls_back_to_proposal():
    proposal = _proposal(target=10.0, stop=8.0)

    decision = _normalize_prices(_decision("hold", target=8.04, stop=8.04), proposal, KLINE)

    assert decision.target_price == 10.0
    assert decision.stop_price == 8.04
    assert decision.prices_estimated is True


def test_valid_pm_prices_are_not_marked_estimated():
    decision = _normalize_prices(_decision("buy", target=10.0, stop=8.0), None, KLINE)

    assert decision.prices_estimated is False


# 早期有一根极端 K 线（高 200 / 低 50），最近 20 根的高点是 120、低点是 90
LONG_KLINE = {
    "kline_data": {
        "items": [{"close": 100.0, "high": 200.0, "low": 50.0}]
        + [{"close": 110.0, "high": 120.0, "low": 90.0}] * 25
    }
}


def test_fallback_uses_recent_bars_not_whole_window():
    decision = _normalize_prices(
        _decision("hold", target=105.0, stop=105.0), None, LONG_KLINE
    )

    assert decision.target_price == 120.0
    assert decision.stop_price == 105.0
    assert decision.prices_estimated is True
