"""使用任务范围内的新闻与公告工具运行真实新闻情绪分析师。"""

from __future__ import annotations

from typing import Any, Mapping

from agents.analysts.tool_agent_runtime import parse_json_report, run_tool_agent
from agents.llm_provider_client import LLMSettings, load_llm_settings
from agents.tools.news_sentiment_analyst.news_data_tools import build_news_tools
from app.schemas.analysis_schemas import AnalysisStage, AnalystFinding, EvidenceItem

_SYSTEM_PROMPT = """你是 FinAgent 的新闻情绪分析师，只分析本次任务提供的新闻和公司公告。
必须先调用 get_news_overview 了解覆盖范围，再按需调用 get_news_items 查看具体标题。
只能依据工具返回的标题、发布日期和来源判断情绪；不要推测未提供的报道内容。
不要分析 K 线技术面或财务数据；不要编造新闻、事件或数据。
每条 key_points 必须引用工具返回的 evidence_ids 中的 ID。
数据不足或覆盖范围有限时降低 confidence，并在 key_points 中说明。
不要给出买入、卖出、仓位或目标价建议。
调用工具拿到数据后，直接输出最终结果；不要输出分析过程、进度说明或"接下来我将…"这类文字。
最终只返回一个 JSON 对象，字段为：
analyst (固定为 "news"), stance (bullish/neutral/bearish), conclusion (string),
key_points (string array), evidence_ids (string array), confidence (0 到 1)。"""

_INSTRUCTION = "请分析下面任务范围内的新闻与公司公告。先调用 get_news_overview，再按需查看具体条目。"


def run_news_sentiment_analyst(
    context: Mapping[str, Any],
    settings: LLMSettings | None = None,
) -> tuple[AnalystFinding, str, list[EvidenceItem]]:
    """生成一份只基于本次任务新闻与公告的结论。"""
    settings = settings or load_llm_settings()
    code = str(context.get("stock_code") or "")
    if not code:
        raise ValueError("分析上下文缺少股票代码")

    tool_schemas, execute_tool, required_tool = build_news_tools(context)
    news = context.get("news_data") or {}
    items = [item for item in (news.get("items") or []) if isinstance(item, dict)]
    kline = context.get("kline_data") or {}
    all_evidence = [
        item for item in context.get("evidence", []) if isinstance(item, EvidenceItem)
    ]
    evidence = next(item for item in all_evidence if item.category == "news")

    task_summary = {
        "stock_code": code,
        "stock_name": kline.get("name"),
        "analysis_start_date": kline.get("actual_start_date"),
        "analysis_end_date": kline.get("actual_end_date"),
        "event_count": len(items),
        "known_data_limitations": evidence.limitations,
    }

    finding, cited_evidence = run_tool_agent(
        settings=settings,
        system_prompt=_SYSTEM_PROMPT,
        task_summary=task_summary,
        instruction=_INSTRUCTION,
        tool_schemas=tool_schemas,
        execute_tool=execute_tool,
        required_tool=required_tool,
        parse_report=lambda content: parse_json_report(content, AnalystFinding),
        citation_ids=lambda report: set(report.evidence_ids),
        candidate_evidence=all_evidence,
    )
    return finding, settings.model_name, cited_evidence


def news_sentiment_analyst_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph 可调用的新闻情绪分析节点。"""
    settings = load_llm_settings(state.get("provider"))
    finding, model_name, cited_evidence = run_news_sentiment_analyst(state, settings)
    return {
        "news_report": finding,
        "evidence": list(state.get("evidence", []))
        + [
            item
            for item in cited_evidence
            if item.evidence_id not in {e.evidence_id for e in state.get("evidence", [])}
        ],
        "sender": "news_sentiment_analyst",
        "current_stage": AnalysisStage.ANALYST,
        "news_model_name": model_name,
    }
