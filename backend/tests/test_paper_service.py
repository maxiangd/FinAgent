"""模拟交易：建仓校验、账户估值、平仓与重置（内存模式，不依赖 Mongo）。"""

from types import SimpleNamespace

import pytest

import app.paper_service as paper
from app.schemas.analysis_schemas import TaskStatus


@pytest.fixture(autouse=True)
def setup_service(monkeypatch):
    monkeypatch.setattr(paper.PaperService, "_collection", lambda self, name: None)
    paper.paper_service._memory_positions.clear()
    paper.paper_service._memory_account = None
    price = {"value": 100.0}
    monkeypatch.setattr(paper, "get_quote", lambda code: {"price": price["value"]})
    return price


def _task(status=TaskStatus.COMPLETED, code="600519", name="贵州茅台", action="hold"):
    result = SimpleNamespace(
        stock_code=code,
        stock_name=name,
        pm_decision=SimpleNamespace(action=action),
    )
    return SimpleNamespace(
        status=status,
        result=result if status == TaskStatus.COMPLETED else None,
    )


def test_quantity_must_be_multiple_of_100(monkeypatch):
    monkeypatch.setattr(paper.task_manager, "get_task", lambda task_id: _task())
    with pytest.raises(ValueError, match="100 的整数倍"):
        paper.paper_service.open_position("task-1", 150)


def test_only_completed_task_can_be_adopted(monkeypatch):
    monkeypatch.setattr(
        paper.task_manager, "get_task", lambda task_id: _task(TaskStatus.FAILED)
    )
    with pytest.raises(ValueError, match="已完成"):
        paper.paper_service.open_position("task-1", 100)


def test_missing_task_raises_lookup_error(monkeypatch):
    monkeypatch.setattr(paper.task_manager, "get_task", lambda task_id: None)
    with pytest.raises(LookupError):
        paper.paper_service.open_position("task-1", 100)


def test_open_position_updates_cash_and_portfolio(monkeypatch):
    monkeypatch.setattr(paper.task_manager, "get_task", lambda task_id: _task())
    position = paper.paper_service.open_position("task-1", 100)

    assert position.entry_price == 100.0
    assert position.quantity == 100

    portfolio = paper.paper_service.get_portfolio()
    assert portfolio.cash == pytest.approx(1_000_000 - 10_000)
    assert portfolio.market_value == pytest.approx(10_000)
    assert portfolio.total_assets == pytest.approx(1_000_000)
    assert len(portfolio.positions) == 1


def test_insufficient_cash_rejected(monkeypatch):
    monkeypatch.setattr(paper.task_manager, "get_task", lambda task_id: _task())
    # 100 元 × 20000 股 = 200 万，超过 100 万初始资金
    with pytest.raises(ValueError, match="资金不足"):
        paper.paper_service.open_position("task-1", 20_000)


def test_close_position_realizes_pnl(monkeypatch, setup_service):
    monkeypatch.setattr(paper.task_manager, "get_task", lambda task_id: _task())
    position = paper.paper_service.open_position("task-1", 100)

    setup_service["value"] = 110.0
    closed = paper.paper_service.close_position(position.position_id)

    assert closed.realized_pnl == pytest.approx(1000.0)
    portfolio = paper.paper_service.get_portfolio()
    assert portfolio.cash == pytest.approx(1_001_000)
    assert portfolio.realized_pnl == pytest.approx(1000.0)
    assert portfolio.positions == []
    assert len(portfolio.closed_positions) == 1


def test_closing_twice_rejected(monkeypatch):
    monkeypatch.setattr(paper.task_manager, "get_task", lambda task_id: _task())
    position = paper.paper_service.open_position("task-1", 100)
    paper.paper_service.close_position(position.position_id)

    with pytest.raises(ValueError, match="已经平仓"):
        paper.paper_service.close_position(position.position_id)


def test_reset_restores_account(monkeypatch):
    monkeypatch.setattr(paper.task_manager, "get_task", lambda task_id: _task())
    paper.paper_service.open_position("task-1", 100)

    portfolio = paper.paper_service.reset()
    assert portfolio.cash == pytest.approx(1_000_000)
    assert portfolio.positions == []
    assert portfolio.realized_pnl == pytest.approx(0.0)
