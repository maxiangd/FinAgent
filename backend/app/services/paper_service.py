"""模拟交易：以 PM 决策为起点建仓、按最新行情估值、支持平仓。

研究演示用途，不接入真实下单。账户与持仓存 MongoDB，不可用时退回进程内。
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.schemas.analysis_schemas import TaskStatus
from app.schemas.paper_schemas import (
    PaperBacktest,
    PaperBacktestObservation,
    PaperBacktestPoint,
    PaperPortfolio,
    PaperPosition,
)
from app.services.task_manager import task_manager
from app.services.task_repository import get_mongo_client, get_mongo_db_name
from data_sources.market.kline_data_service import get_kline
from data_sources.market.market_snapshot_service import get_quote

logger = logging.getLogger("finagent.paper")

INITIAL_CASH = 1_000_000.0
ACCOUNT_COLLECTION = "paper_account"
POSITION_COLLECTION = "paper_positions"
ACCOUNT_ID = "default"

# 回测默认持有期（交易日）
DEFAULT_BACKTEST_HORIZONS = (1, 5, 10, 20)
MAX_BACKTEST_HORIZON = 250


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Mongo 读出来的时间是 naive UTC，统一补上时区再参与计算。"""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _holding_days(opened_at: datetime, closed_at: datetime | None = None) -> int:
    end = _as_utc(closed_at) if closed_at else _now()
    return max((end - _as_utc(opened_at)).days, 0)


def _normalize_horizons(horizons: list[int] | None) -> list[int]:
    if not horizons:
        return list(DEFAULT_BACKTEST_HORIZONS)
    try:
        cleaned = sorted({int(item) for item in horizons})
    except (TypeError, ValueError) as exc:
        raise ValueError("持有期必须是交易日数，例如 1,5,10,20") from exc
    if not cleaned or cleaned[0] < 1 or cleaned[-1] > MAX_BACKTEST_HORIZON:
        raise ValueError(f"持有期必须在 1 到 {MAX_BACKTEST_HORIZON} 个交易日之间")
    return cleaned


class PaperService:
    """账户与持仓的业务逻辑与存储。"""

    def __init__(self) -> None:
        self._memory_positions: dict[str, dict[str, Any]] = {}
        self._memory_account: dict[str, Any] | None = None
        self._lock = threading.Lock()

    # ---------- 存储 ----------
    def _collection(self, name: str):
        client = get_mongo_client()
        return client[get_mongo_db_name()][name] if client is not None else None

    def _load_account(self) -> dict[str, Any]:
        collection = self._collection(ACCOUNT_COLLECTION)
        if collection is not None:
            document = collection.find_one({"account_id": ACCOUNT_ID})
            if document:
                return document
            document = {
                "account_id": ACCOUNT_ID,
                "initial_cash": INITIAL_CASH,
                "cash": INITIAL_CASH,
                "realized_pnl": 0.0,
            }
            collection.update_one(
                {"account_id": ACCOUNT_ID}, {"$setOnInsert": document}, upsert=True
            )
            return document
        if self._memory_account is None:
            self._memory_account = {
                "initial_cash": INITIAL_CASH,
                "cash": INITIAL_CASH,
                "realized_pnl": 0.0,
            }
        return dict(self._memory_account)

    def _save_account(self, account: dict[str, Any]) -> None:
        collection = self._collection(ACCOUNT_COLLECTION)
        if collection is not None:
            collection.update_one(
                {"account_id": ACCOUNT_ID}, {"$set": account}, upsert=True
            )
        else:
            self._memory_account = dict(account)

    def _list_positions(self, status: str | None = None) -> list[dict[str, Any]]:
        collection = self._collection(POSITION_COLLECTION)
        if collection is not None:
            query = {"status": status} if status else {}
            return list(collection.find(query).sort("opened_at", -1))
        with self._lock:
            items = list(self._memory_positions.values())
        if status:
            items = [item for item in items if item.get("status") == status]
        return sorted(items, key=lambda item: item.get("opened_at"), reverse=True)

    def _get_position(self, position_id: str) -> dict[str, Any] | None:
        collection = self._collection(POSITION_COLLECTION)
        if collection is not None:
            return collection.find_one({"position_id": position_id})
        with self._lock:
            return self._memory_positions.get(position_id)

    def _save_position(self, document: dict[str, Any]) -> None:
        collection = self._collection(POSITION_COLLECTION)
        if collection is not None:
            collection.update_one(
                {"position_id": document["position_id"]}, {"$set": document}, upsert=True
            )
        else:
            with self._lock:
                self._memory_positions[document["position_id"]] = dict(document)

    # ---------- 业务 ----------
    def open_position(self, task_id: str, quantity: int) -> PaperPosition:
        """采纳某次已完成分析任务的 PM 结论，按最新价建仓。"""
        if quantity % 100 != 0:
            raise ValueError("数量必须是 100 的整数倍")

        task = task_manager.get_task(task_id)
        if task is None:
            raise LookupError(f"任务不存在：{task_id}")
        if task.status != TaskStatus.COMPLETED or task.result is None:
            raise ValueError("只能采纳已完成的分析任务")

        result = task.result
        quote = get_quote(result.stock_code)
        price = quote.get("price")
        if price is None:
            raise LookupError(f"{result.stock_code} 暂无最新报价，稍后再试")

        cost = round(price * quantity, 2)
        with self._lock:
            account = self._load_account()
            if cost > float(account["cash"]) + 1e-6:
                raise ValueError(
                    f"可用资金不足：需要 {cost:,.2f} 元，当前现金 {float(account['cash']):,.2f} 元"
                )
            account["cash"] = round(float(account["cash"]) - cost, 2)
            self._save_account(account)

        document = {
            "position_id": uuid4().hex,
            "task_id": task_id,
            "stock_code": result.stock_code,
            "stock_name": result.stock_name,
            "quantity": quantity,
            "entry_price": price,
            "status": "open",
            "pm_action": result.pm_decision.action if result.pm_decision else None,
            "opened_at": _now(),
            "closed_at": None,
            "close_price": None,
            "realized_pnl": None,
        }
        self._save_position(document)
        return self._to_model(document, current_price=price)

    def close_position(self, position_id: str) -> PaperPosition:
        document = self._get_position(position_id)
        if document is None:
            raise LookupError(f"持仓不存在：{position_id}")
        if document.get("status") != "open":
            raise ValueError("该持仓已经平仓")

        quote = get_quote(document["stock_code"])
        price = quote.get("price")
        if price is None:
            raise LookupError(f"{document['stock_code']} 暂无最新报价，稍后再试")

        pnl = round((price - document["entry_price"]) * document["quantity"], 2)
        with self._lock:
            account = self._load_account()
            account["cash"] = round(
                float(account["cash"]) + price * document["quantity"], 2
            )
            account["realized_pnl"] = round(float(account["realized_pnl"]) + pnl, 2)
            self._save_account(account)

        document.update(
            status="closed",
            closed_at=_now(),
            close_price=price,
            realized_pnl=pnl,
        )
        self._save_position(document)
        return self._to_model(document)

    def backtest_task(
        self,
        task_id: str,
        horizons: list[int] | None = None,
        as_of: date | None = None,
    ) -> PaperBacktest:
        """分析窗口结束日买入，统计到观察日（默认今天）的涨幅与固定持有期收益。"""
        horizons = _normalize_horizons(horizons)
        task = task_manager.get_task(task_id)
        if task is None:
            raise LookupError(f"任务不存在：{task_id}")
        if task.status != TaskStatus.COMPLETED or task.result is None:
            raise ValueError("只能回测已完成的分析任务")

        result = task.result
        entry_date = result.actual_end_date
        if as_of is None:
            as_of = date.today()
        elif as_of > date.today():
            raise ValueError("观察日不能晚于今天")
        if as_of < entry_date:
            raise ValueError(f"观察日不能早于分析窗口结束日 {entry_date}")

        try:
            kline = get_kline(
                result.stock_code,
                period="daily",
                start_date=entry_date - timedelta(days=15),
                end_date=date.today(),
            )
        except LookupError as exc:
            raise LookupError(f"{result.stock_code} 缺少回测所需行情：{exc}") from exc

        dates: list[str] = kline["dates"]
        items: list[dict[str, Any]] = kline["items"]

        def last_bar_on_or_before(target: date) -> int | None:
            return next(
                (
                    index
                    for index in range(len(dates) - 1, -1, -1)
                    if dates[index] <= target.isoformat()
                    and items[index].get("close") is not None
                ),
                None,
            )

        start_index = last_bar_on_or_before(entry_date)
        if start_index is None:
            raise LookupError(f"{result.stock_code} 在 {entry_date} 之前没有可用行情")

        actual_entry_date = date.fromisoformat(dates[start_index])
        entry_price = float(items[start_index]["close"])
        notes: list[str] = []
        if actual_entry_date != entry_date:
            notes.append(
                f"分析窗口结束日 {entry_date} 无交易行情，按之前最近交易日 {actual_entry_date} 收盘价买入"
            )

        observation = None
        observation_index = last_bar_on_or_before(as_of)
        if observation_index is not None and observation_index >= start_index:
            observation_date = date.fromisoformat(dates[observation_index])
            observation_close = float(items[observation_index]["close"])
            observation = PaperBacktestObservation(
                target_date=observation_date,
                close_price=observation_close,
                trading_days=observation_index - start_index,
                calendar_days=(observation_date - actual_entry_date).days,
                return_pct=round(
                    (observation_close - entry_price) / entry_price * 100, 2
                ),
            )
            if observation_date != as_of:
                notes.append(f"观察日 {as_of} 无交易行情，按最近交易日 {observation_date} 计算")

        points: list[PaperBacktestPoint] = []
        for horizon in horizons:
            target_index = start_index + horizon
            target_close = (
                items[target_index].get("close") if target_index < len(items) else None
            )
            if target_close is None:
                points.append(PaperBacktestPoint(horizon_days=horizon))
                continue
            points.append(
                PaperBacktestPoint(
                    horizon_days=horizon,
                    target_date=date.fromisoformat(dates[target_index]),
                    close_price=float(target_close),
                    return_pct=round(
                        (float(target_close) - entry_price) / entry_price * 100, 2
                    ),
                )
            )

        return PaperBacktest(
            task_id=task_id,
            stock_code=result.stock_code,
            stock_name=result.stock_name,
            entry_date=actual_entry_date,
            entry_price=entry_price,
            observation=observation,
            points=points,
            note="；".join(notes) or None,
        )

    def get_portfolio(self) -> PaperPortfolio:
        account = self._load_account()
        open_positions = []
        market_value = 0.0
        unrealized_pnl = 0.0
        for document in self._list_positions("open"):
            quote = get_quote(document["stock_code"])
            price = quote.get("price")
            value = round(price * document["quantity"], 2) if price is not None else None
            pnl = (
                round((price - document["entry_price"]) * document["quantity"], 2)
                if price is not None
                else None
            )
            if value is not None:
                market_value += value
            if pnl is not None:
                unrealized_pnl += pnl
            open_positions.append(
                self._to_model(
                    document,
                    current_price=price,
                    market_value=value,
                    unrealized_pnl=pnl,
                )
            )

        closed_positions = [
            self._to_model(document) for document in self._list_positions("closed")[:20]
        ]
        cash = round(float(account["cash"]), 2)
        total_assets = round(cash + market_value, 2)
        return PaperPortfolio(
            initial_cash=float(account["initial_cash"]),
            cash=cash,
            market_value=round(market_value, 2),
            total_assets=total_assets,
            unrealized_pnl=round(unrealized_pnl, 2),
            realized_pnl=round(float(account["realized_pnl"]), 2),
            total_pnl=round(total_assets - float(account["initial_cash"]), 2),
            positions=open_positions,
            closed_positions=closed_positions,
        )

    def reset(self) -> PaperPortfolio:
        """清空持仓并把现金恢复到初始值（演示用）。"""
        collection = self._collection(POSITION_COLLECTION)
        if collection is not None:
            collection.delete_many({})
        with self._lock:
            self._memory_positions.clear()
            self._memory_account = None
        self._save_account(
            {
                "account_id": ACCOUNT_ID,
                "initial_cash": INITIAL_CASH,
                "cash": INITIAL_CASH,
                "realized_pnl": 0.0,
            }
        )
        return self.get_portfolio()

    def _to_model(
        self,
        document: dict[str, Any],
        current_price: float | None = None,
        market_value: float | None = None,
        unrealized_pnl: float | None = None,
    ) -> PaperPosition:
        pct = None
        cost = document["entry_price"] * document["quantity"]
        if unrealized_pnl is not None and cost:
            pct = round(unrealized_pnl / cost * 100, 2)
        return PaperPosition(
            position_id=document["position_id"],
            task_id=document["task_id"],
            stock_code=document["stock_code"],
            stock_name=document.get("stock_name"),
            quantity=document["quantity"],
            entry_price=document["entry_price"],
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=pct,
            status=document.get("status", "open"),
            pm_action=document.get("pm_action"),
            opened_at=document["opened_at"],
            holding_days=_holding_days(
                document["opened_at"], document.get("closed_at")
            ),
            closed_at=document.get("closed_at"),
            close_price=document.get("close_price"),
            realized_pnl=document.get("realized_pnl"),
        )


paper_service = PaperService()
