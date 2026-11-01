"""使用任务范围内的基本面工具运行真实基本面分析师。"""

from __future__ import annotations

from typing import Any, Mapping

from agents.roles.analysts.tool_agent_runtime import parse_json_report, run_tool_agent
from agents.llm_provider_client import LLMSettings, load_llm_settings
from agents.tools.fundamental_analyst.fundamental_data_tools import build_fundamental_tools
from app.schemas.analysis_schemas import AnalysisStage, AnalystFinding, EvidenceItem

_SYSTEM_PROMPT = """你是 FinAgent 的基本面分析师，只分析本次任务提供的基本面数据。
必须先调用工具读取数据，再给出结论。
历史模式下数据按报告期和公告日期整理，只能反映所选区间内已经公开的财报；
当前模式下的指标是当前快照，不能用来解释过去某个日期的判断。
不要分析 K 线技术面、新闻、公司公告或宏观因素；不要编造未提供的数值、比率或结论。
每条 key_points 必须引用工具返回的 evidence_ids 中的 ID。
数据不足时降低 confidence，并在 key_points 中说明缺少哪些数据。
不要给出买入、卖出、仓位或目标价建议。
调用工具拿到数据后，直接输出最终结果；不要输出分析过程、进度说明或"接下来我将…"这类文字。
最终只返回一个 JSON 对象，字段为：
analyst (固定为 "fundamental"), stance (bullish/neutral/bearish), conclusion (string),
key_points (string array), evidence_ids (string array), confidence (0 到 1)。"""

_INSTRUCTION = "请分析下面任务范围内的基本面数据。先调用工具读取数据，再给出结论。"


def run_fundamental_analyst(
    context: Mapping[str, Any],
    settings: LLMSettings | None = None,
) -> tuple[AnalystFinding, str, list[EvidenceItem]]:
    """生成一份只基于本次任务基本面数据的结论。"""
    settings = settings or load_llm_settings()
    code = str(context.get("stock_code") or "")
    if not code:
        raise ValueError("分析上下文缺少股票代码")

    tool_schemas, execute_tool, required_tool = build_fundamental_tools(context)
    data = context.get("fundamentals_data") or {}
    mode = "historical" if ("baseline" in data or "reports_in_range" in data) else "current"
    kline = context.get("kline_data") or {}
    all_evidence = [
        item for item in context.get("evidence", []) if isinstance(item, EvidenceItem)
    ]
    evidence = next(item for item in all_evidence if item.category == "fundamental")

    task_summary = {
        "stock_code": code,
        "stock_name": kline.get("name"),
        "mode": mode,
        "analysis_start_date": kline.get("actual_start_date"),
        "analysis_end_date": kline.get("actual_end_date"),
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


def fundamental_analyst_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph 可调用的基本面分析节点。"""
    settings = load_llm_settings(state.get("provider"))
    finding, model_name, cited_evidence = run_fundamental_analyst(state, settings)
    return {
        "fundamentals_report": finding,
        "evidence": list(state.get("evidence", []))
        + [
            item
            for item in cited_evidence
            if item.evidence_id not in {e.evidence_id for e in state.get("evidence", [])}
        ],
        "sender": "fundamental_analyst",
        "current_stage": AnalysisStage.ANALYST,
        "fundamental_model_name": model_name,
    }
