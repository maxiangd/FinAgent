"""把 Agent 状态整理成接口响应。"""

from __future__ import annotations

from app.schemas.analysis_schemas import (
    AnalysisRunResponse,
    AnalysisStage,
    AnalysisTaskRequest,
    DataIngestionItem,
    DataIngestionResponse,
)

_PERIOD_LABELS = {"daily": "日K", "weekly": "周K", "monthly": "月K"}


def _fmt_pct(value) -> str:
    """格式化财务百分比；无数据时显示暂无。"""
    if value is None:
        return "暂无"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "暂无"


def _fmt_number(value, digits: int = 2, suffix: str = "") -> str:
    """格式化行情快照数字；无数据时显示暂无。"""
    if value is None:
        return "暂无"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "暂无"


def build_ingestion_response(request: AnalysisTaskRequest, state: dict) -> DataIngestionResponse:
    """把 Agent 初始状态整理成前端数据接入阶段需要的摘要。"""
    kline = state.get("kline_data") or {}
    fundamentals = state.get("fundamentals_data") or {}
    news = state.get("news_data") or {}
    market_snapshot = state.get("market_snapshot") or {}
    kline_items = kline.get("items") or []
    warmup_items = kline.get("warmup") or []
    requested_start = request.start_date or request.analysis_date
    requested_end = request.end_date or request.analysis_date
    actual_start = state.get("actual_start_date")
    actual_end = state.get("actual_end_date")
    historical_request = requested_start is not None

    items = [
        DataIngestionItem(
            name="K线行情",
            note=(
                f"{kline.get('source') or '行情服务'} · {actual_start} 至 {actual_end} · "
                f"{len(kline_items)} 根{_PERIOD_LABELS[request.period]}，"
                f"另有 {len(warmup_items)} 根预热数据"
            ),
            status="success" if kline_items else "failed",
        )
    ]

    if historical_request:
        baseline = fundamentals.get("baseline")
        reports = fundamentals.get("reports_in_range") or []
        if baseline:
            baseline_note = (
                f"区间开始前已披露：{baseline.get('report_date')} 财报 "
                f"（公告日 {baseline.get('publication_date')}）"
            )
        else:
            baseline_note = "没有找到区间开始前可用的财务基线"
        financial_note = f"{baseline_note}；区间内新披露 {len(reports)} 份"
        if reports:
            financial_note += "：" + "、".join(
                f"{report.get('report_date')}（{report.get('publication_date')}）"
                for report in reports[:4]
            )
            if len(reports) > 4:
                financial_note += f" 等，共 {len(reports)} 份"
        financial_ready = bool(baseline or reports)
    else:
        available_metrics = [
            ("ROE", fundamentals.get("roe")),
            ("营收增速", fundamentals.get("revGrowth")),
            ("净利增速", fundamentals.get("profitGrowth")),
            ("毛利率", fundamentals.get("margin")),
        ]
        financial_note = " · ".join(
            f"{label} {_fmt_pct(value)}" for label, value in available_metrics
        )
        financial_ready = any(value is not None for _, value in available_metrics)

    items.append(
        DataIngestionItem(
            name="基本面数据",
            note=financial_note,
            status="success" if financial_ready else "partial",
        )
    )

    news_items = news.get("items") or []
    media_count = sum(
        1 for entry in news_items
        if entry.get("kind") == "news" or not entry.get("kind")
    )
    announcement_count = sum(
        1 for entry in news_items if entry.get("kind") == "company_announcement"
    )
    news_note = f"媒体新闻 {media_count} 条 · 巨潮公司公告 {announcement_count} 条"
    news_limitations = news.get("limitations") or []
    items.append(
        DataIngestionItem(
            name="新闻与公司公告",
            note=news_note,
            status="success" if news_items and not news_limitations else "partial",
        )
    )

    evidence = state.get("evidence") or []
    limitations: list[str] = []
    for evidence_item in evidence:
        item_limitations = getattr(evidence_item, "limitations", None)
        if item_limitations is None and isinstance(evidence_item, dict):
            item_limitations = evidence_item.get("limitations") or []
        for limitation in item_limitations or []:
            if limitation not in limitations:
                limitations.append(limitation)

    actual_start_text = actual_start.isoformat() if actual_start else "暂无"
    actual_end_text = actual_end.isoformat() if actual_end else "暂无"
    requested_range_text = (
        f"{requested_start} 至 {requested_end}"
        if requested_start and requested_end
        else "最新可用数据"
    )
    meta = {
        "分析周期": _PERIOD_LABELS[request.period],
        "请求区间": requested_range_text,
        "实际K线区间": f"{actual_start_text} 至 {actual_end_text}",
        "K线数量": f"{len(kline_items)} 根",
        "预热数据": f"{len(warmup_items)} 根",
        "K线来源": kline.get("source") or "行情服务",
    }
    if not historical_request:
        meta.update(
            {
                "当前价格": _fmt_number(market_snapshot.get("price"), 2, " 元"),
                "当日涨跌": _fmt_pct(market_snapshot.get("changePct")),
                "市值": market_snapshot.get("marketCap") or "暂无",
                "PE(TTM)": _fmt_number(fundamentals.get("pe"), 2),
                "ROE": _fmt_pct(fundamentals.get("roe")),
                "股息率": _fmt_pct(fundamentals.get("dividendYield")),
                "量比": _fmt_number(market_snapshot.get("volRatio"), 2),
            }
        )

    stock_name = market_snapshot.get("name") or kline.get("name")
    displayed_news = dict(news)
    displayed_news["total_count"] = len(news_items)
    displayed_news["items"] = news_items

    return DataIngestionResponse(
        stock_code=request.stock_code,
        stock_name=stock_name,
        period=request.period,
        requested_start_date=requested_start,
        requested_end_date=requested_end,
        actual_start_date=actual_start,
        actual_end_date=actual_end,
        items=items,
        meta=meta,
        fundamentals_data=fundamentals,
        news_data=displayed_news,
        limitations=limitations,
    )


def build_run_response(
    request: AnalysisTaskRequest,
    state: dict,
    task_id: str,
) -> AnalysisRunResponse:
    """把工作流的最终状态整理成运行摘要。"""
    evidence = list(state.get("evidence") or [])
    kline = state.get("kline_data") or {}
    debate_state = state.get("investment_debate_state") or {}
    risk_state = state.get("risk_debate_state") or {}
    model_names = {
        key: value
        for key, value in {
            "market": state.get("market_model_name"),
            "fundamental": state.get("fundamental_model_name"),
            "news": state.get("news_model_name"),
        }.items()
        if value
    }
    return AnalysisRunResponse(
        task_id=task_id,
        stock_code=request.stock_code,
        stock_name=kline.get("name"),
        period=request.period,
        actual_start_date=state["actual_start_date"],
        actual_end_date=state["actual_end_date"],
        current_stage=state.get("current_stage") or AnalysisStage.PM,
        sender=state.get("sender"),
        provider=state.get("market_provider"),
        ingestion=build_ingestion_response(request, state),
        market_report=state["market_report"],
        fundamental_report=state.get("fundamentals_report"),
        news_report=state.get("news_report"),
        debate_turns=list(debate_state.get("history") or []),
        trade_proposal=state.get("trade_proposal"),
        risk_reviews=list(risk_state.get("history") or []),
        pm_decision=state.get("pm_decision"),
        model_names=model_names,
        evidence=evidence,
        limitations=list(dict.fromkeys(
            limitation
            for item in evidence
            for limitation in item.limitations
        )),
        errors=list(state.get("errors") or []),
    )
