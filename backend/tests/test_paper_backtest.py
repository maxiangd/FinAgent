"""模拟交易：持有天数与买入后固定持有期收益回测。"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.services.paper_service as paper
from app.schemas.analysis_schemas import TaskStatus

DATES = [
    "2026-10-20",
    "2026-10-21",
    "2026-10-22",
    "2026-10-23",
    "2026-10-26",
    "2026-10-27",
]
CLOSES = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]


def _task(status=TaskStatus.COMPLETED, end_date=date(2026, 10, 20)):
    result = SimpleNamespace(
        stock_code="600519",
        stock_name="贵州茅台",
        actual_end_date=end_date,
    )
    return SimpleNamespace(status=status, result=result if status == TaskStatus.COMPLETED else None)


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(
        paper,
        "get_kline",
        lambda code, **kwargs: {
            "dates": DATES,
            "items": [{"close": close} for close in CLOSES],
        },
    )
    monkeypatch.setattr(paper.task_manager, "get_task", lambda task_id: _task())


AS_OF = date(2026, 10, 27)


def test_backtest_returns_observation_and_forward_returns():
    result = paper.paper_service.backtest_task("task-1", [1, 5], AS_OF)

    assert result.entry_date == date(2026, 10, 20)
    assert result.entry_price == 100.0
    assert result.observation.target_date == date(2026, 10, 27)
    assert result.observation.trading_days == 5
    assert result.observation.calendar_days == 7
    assert result.observation.return_pct == 5.0
    assert [point.return_pct for point in result.points] == [1.0, 5.0]
    assert result.note is None


def test_horizon_beyond_available_data_is_empty():
    result = paper.paper_service.backtest_task("task-1", [10], AS_OF)

    point = result.points[0]
    assert point.return_pct is None
    assert point.close_price is None
    assert point.target_date is None


def test_observation_on_non_trading_day_uses_previous_bar():
    result = paper.paper_service.backtest_task("task-1", [1], date(2026, 10, 24))

    assert result.observation.target_date == date(2026, 10, 23)
    assert result.observation.trading_days == 3
    assert result.observation.return_pct == 3.0
    assert "2026-10-24" in result.note


def test_window_end_on_non_trading_day_uses_previous_bar(monkeypatch):
    monkeypatch.setattr(
        paper.task_manager,
        "get_task",
        lambda task_id: _task(end_date=date(2026, 10, 24)),
    )

    result = paper.paper_service.backtest_task("task-1", [1], AS_OF)

    assert result.entry_date == date(2026, 10, 23)
    assert result.entry_price == 103.0
    assert "2026-10-24" in result.note


def test_observation_after_available_data_uses_last_bar():
    result = paper.paper_service.backtest_task("task-1", [1], date(2026, 10, 30))

    assert result.observation.target_date == date(2026, 10, 27)
    assert result.observation.trading_days == 5
    assert "2026-10-30" in result.note


def test_unfinished_task_is_rejected(monkeypatch):
    monkeypatch.setattr(
        paper.task_manager,
        "get_task",
        lambda task_id: _task(status=TaskStatus.FAILED),
    )

    with pytest.raises(ValueError, match="已完成"):
        paper.paper_service.backtest_task("task-1", [1], AS_OF)


def test_observation_before_window_end_is_rejected():
    with pytest.raises(ValueError, match="不能早于分析窗口结束日"):
        paper.paper_service.backtest_task("task-1", [1], date(2026, 10, 19))


def test_future_observation_is_rejected():
    with pytest.raises(ValueError, match="不能晚于今天"):
        paper.paper_service.backtest_task(
            "task-1", [1], date.today() + timedelta(days=1)
        )


def test_invalid_horizon_is_rejected():
    with pytest.raises(ValueError, match="1 到 250"):
        paper.paper_service.backtest_task("task-1", [0])


def test_holding_days_uses_open_and_close_time():
    opened = datetime.now(timezone.utc) - timedelta(days=7)

    assert paper._holding_days(opened) == 7
    assert paper._holding_days(opened, opened + timedelta(days=3)) == 3


def test_holding_days_accepts_naive_utc():
    opened = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) - timedelta(days=2)

    assert paper._holding_days(opened) == 2
