"""使用任务范围内的行情工具运行真实市场分析师。"""

from __future__ import annotations

from typing import Any, Mapping

from agents.roles.analysts.tool_agent_runtime import (
    parse_json_payload,
    run_tool_agent,
    validate_report,
)
from agents.llm_provider_client import LLMSettings, load_llm_settings
from agents.tools.market_analyst.market_data_tools import build_market_tools
from app.schemas.analysis_schemas import AnalysisStage, EvidenceItem, MarketAnalystReport

_SYSTEM_PROMPT = """你是 FinAgent 的行情分析师，只分析本次任务提供的股票 K 线和技术面。
必须先调用 get_window_statistics 获取所选窗口的统计，再按需调用 get_kline_bars 查看区间内的 K 线细节。
工具只能读取用户选择的分析区间；预热 K 线仅用于均线计算，不能当作所选区间内的行情事件。
不要分析基本面、新闻、公司公告或宏观因素；不要编造未提供的指标、价位、原因或数据。
区间涨幅、均线和回撤等数值应直接依据工具结果。每条 key_points 都必须引用工具返回的 evidence_ids。
当区间数据不足以支持判断时，降低 confidence 并在 data_gaps 中说明。
不要给出买入、卖出、仓位或目标价建议。
调用工具拿到数据后，直接输出最终结果；不要输出分析过程、进度说明或"接下来我将…"这类文字。
最终只返回一个 JSON 对象，字段为：
stance (bullish/neutral/bearish), conclusion (string), key_points (array),
confidence (0 到 1), data_gaps (string array)。
key_points 的每个元素必须是对象，形如 {"text": "结论", "evidence_ids": ["证据 id"]}；
evidence_ids 只能放在每个 key_points 元素内部，不要在顶层另加 evidence_ids 字段。"""

_INSTRUCTION = "请分析下面任务范围内的 K 线。先使用工具读取统计，再按需要查询 K 线细节。"


def _parse_market_report(content: Any) -> MarketAnalystReport:
    """解析行情报告；兼容模型把 evidence_ids 写在顶层、key_points 内缺失的情况。"""
    payload = parse_json_payload(content)
    top_level_ids = payload.pop("evidence_ids", None)
    points = payload.get("key_points")
    if isinstance(points, list):
        for point in points:
            if isinstance(point, dict):
                point.setdefault("evidence_ids", list(top_level_ids or []))
    return validate_report(payload, MarketAnalystReport)


def run_market_analyst(
    context: Mapping[str, Any],
    settings: LLMSettings | None = None,
) -> tuple[MarketAnalystReport, str, list[EvidenceItem]]:
    """通过受限工具调用生成一份只基于所选 K 线区间的市场分析。"""
    settings = settings or load_llm_settings()
    kline = context.get("kline_data") or {}
    code = str(context.get("stock_code") or kline.get("code") or "")
    if not code:
        raise ValueError("分析上下文缺少股票代码")

    tool_schemas, execute_tool, market_evidence = build_market_tools(context)
    all_evidence = [
        item for item in context.get("evidence", []) if isinstance(item, EvidenceItem)
    ]
    all_evidence.extend(
        item for item in market_evidence if item.evidence_id not in {e.evidence_id for e in all_evidence}
    )

    task_summary = {
        "stock_code": code,
        "stock_name": kline.get("name"),
        "period": kline.get("period"),
        "selected_start_date": kline.get("actual_start_date"),
        "selected_end_date": kline.get("actual_end_date"),
        "selected_bar_count": len(kline.get("items") or []),
        "known_data_limitations": [
            limitation
            for item in all_evidence
            for limitation in item.limitations
        ],
    }

    report, cited_evidence = run_tool_agent(
        settings=settings,
        system_prompt=_SYSTEM_PROMPT,
        task_summary=task_summary,
        instruction=_INSTRUCTION,
        tool_schemas=tool_schemas,
        execute_tool=execute_tool,
        required_tool="get_window_statistics",
        parse_report=_parse_market_report,
        citation_ids=lambda report: {
            evidence_id
            for point in report.key_points
            for evidence_id in point.evidence_ids
        },
        candidate_evidence=all_evidence,
    )
    return report, settings.model_name, cited_evidence


def market_analyst_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph 可调用的行情分析节点，返回结构化结论和引用证据。"""
    settings = load_llm_settings(state.get("provider"))
    report, model_name, cited_evidence = run_market_analyst(state, settings)
    return {
        "market_report": report,
        "market_report_evidence": cited_evidence,
        "evidence": list(state.get("evidence", []))
        + [
            item
            for item in cited_evidence
            if item.evidence_id not in {e.evidence_id for e in state.get("evidence", [])}
        ],
        "sender": "market_analyst",
        "current_stage": AnalysisStage.ANALYST,
        "market_model_name": model_name,
        "market_provider": settings.provider,
    }
