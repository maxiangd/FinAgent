"""交易提案价位兜底：模型漏填时用区间高低点补齐。"""

from agents.roles.trader.trader_agent import _fill_missing_prices
from app.schemas.analysis_schemas import TradeProposal


def _context():
    return {
        "kline_data": {
            "items": [
                {"open": 100.0, "close": 101.0, "high": 105.0, "low": 98.0, "volume": 1},
                {"open": 101.0, "close": 110.0, "high": 112.0, "low": 100.0, "volume": 1},
            ]
        }
    }


def test_buy_fills_prices_from_range():
    proposal = TradeProposal(action="buy", rationale="测试", evidence_ids=[])
    filled = _fill_missing_prices(proposal, _context())

    assert filled.entry_price == 110.0   # 最新收盘价
    assert filled.target_price == 112.0  # 区间最高
    assert filled.stop_price == 98.0     # 区间最低


def test_reduce_swaps_target_and_stop():
    proposal = TradeProposal(action="reduce", rationale="测试", evidence_ids=[])
    filled = _fill_missing_prices(proposal, _context())

    assert filled.target_price == 98.0
    assert filled.stop_price == 112.0


def test_existing_prices_are_kept():
    proposal = TradeProposal(
        action="buy",
        rationale="测试",
        entry_price=108.0,
        target_price=120.0,
        stop_price=104.0,
        evidence_ids=[],
    )
    filled = _fill_missing_prices(proposal, _context())

    assert (filled.entry_price, filled.target_price, filled.stop_price) == (108.0, 120.0, 104.0)
    assert filled.prices_estimated is False


def test_partial_prices_are_completed():
    proposal = TradeProposal(
        action="buy", rationale="测试", entry_price=108.0, evidence_ids=[]
    )
    filled = _fill_missing_prices(proposal, _context())

    assert filled.entry_price == 108.0
    assert filled.target_price == 112.0
    assert filled.stop_price == 98.0


def test_prices_in_wrong_direction_are_replaced():
    proposal = TradeProposal(
        action="buy",
        rationale="测试",
        entry_price=110.0,
        target_price=100.0,
        stop_price=120.0,
        evidence_ids=[],
    )
    filled = _fill_missing_prices(proposal, _context())

    assert filled.target_price == 112.0
    assert filled.stop_price == 98.0


def test_equal_prices_are_disambiguated():
    proposal = TradeProposal(
        action="hold",
        rationale="测试",
        entry_price=110.0,
        target_price=120.0,
        stop_price=120.0,
        evidence_ids=[],
    )
    filled = _fill_missing_prices(proposal, _context())

    assert filled.target_price == 120.0
    assert filled.stop_price == 98.0
    assert filled.prices_estimated is True


def test_fallback_uses_recent_bars_not_whole_window():
    # 早期极端 K 线高 200 / 低 50，最近 20 根高 120 / 低 90，最新收盘 110
    context = {
        "kline_data": {
            "items": [{"close": 100.0, "high": 200.0, "low": 50.0}]
            + [{"close": 110.0, "high": 120.0, "low": 90.0}] * 25
        }
    }
    proposal = TradeProposal(action="buy", rationale="测试", evidence_ids=[])

    filled = _fill_missing_prices(proposal, context)

    assert filled.entry_price == 110.0
    assert filled.target_price == 120.0
    assert filled.stop_price == 90.0
    assert filled.prices_estimated is True
