"""模拟交易的数据模型（研究演示，不接入真实下单）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaperPositionCreate(BaseModel):
    """从某次已完成的分析任务采纳一个模拟持仓。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=8, max_length=64)
    quantity: int = Field(ge=100, le=1_000_000, description="股数，须为 100 的整数倍")


class PaperPosition(BaseModel):
    """一条模拟持仓记录。"""

    model_config = ConfigDict(extra="forbid")

    position_id: str
    task_id: str
    stock_code: str
    stock_name: str | None = None
    quantity: int
    entry_price: float
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    status: Literal["open", "closed"] = "open"
    pm_action: str | None = None
    opened_at: datetime
    holding_days: int | None = None
    closed_at: datetime | None = None
    close_price: float | None = None
    realized_pnl: float | None = None


class PaperPortfolio(BaseModel):
    """账户快照：现金、持仓市值与盈亏。"""

    model_config = ConfigDict(extra="forbid")

    initial_cash: float
    cash: float
    market_value: float
    total_assets: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    positions: list[PaperPosition] = Field(default_factory=list)
    closed_positions: list[PaperPosition] = Field(default_factory=list)


class PaperBacktestPoint(BaseModel):
    """买入后第 N 个交易日的收盘表现；行情不足时价格与收益为空。"""

    model_config = ConfigDict(extra="forbid")

    horizon_days: int
    target_date: date | None = None
    close_price: float | None = None
    return_pct: float | None = None


class PaperBacktestObservation(BaseModel):
    """分析窗口结束日至观察日的收盘涨幅。"""

    model_config = ConfigDict(extra="forbid")

    target_date: date
    close_price: float
    trading_days: int
    calendar_days: int
    return_pct: float


class PaperBacktest(BaseModel):
    """以分析窗口结束日收盘价买入后的观察期与固定持有期收益。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    stock_code: str
    stock_name: str | None = None
    entry_date: date
    entry_price: float
    observation: PaperBacktestObservation | None = None
    points: list[PaperBacktestPoint] = Field(default_factory=list)
    note: str | None = None
