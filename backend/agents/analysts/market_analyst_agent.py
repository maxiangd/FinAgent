"""使用任务范围内的行情工具运行真实市场分析师。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping

from agents.llm_provider_client import (
    LLMCallError,
    LLMSettings,
    load_llm_settings,
    request_chat_completion,
)
from agents.tools.market_analyst.market_data_tools import build_market_tools
from app.schemas.analysis_schemas import AnalysisStage, EvidenceItem, MarketAnalystReport

logger = logging.getLogger("finagent.analyst.market")


MAX_TOOL_ROUNDS = 5
MAX_TOOL_CALLS = 8
MAX_JSON_REPAIRS = 2

_JSON_REPAIR_PROMPT = (
    "现在直接输出最终结论：只返回一个 JSON 对象，字段为 stance、conclusion、"
    "key_points、confidence、data_gaps。不要输出解释、标题、列表、进度说明或后续计划。"
)

_SYSTEM_PROMPT = """你是 FinAgent 的行情分析师，只分析本次任务提供的股票 K 线和技术面。
必须先调用 get_window_statistics 获取所选窗口的统计，再按需调用 get_kline_bars 查看区间内的 K 线细节。
工具只能读取用户选择的分析区间；预热 K 线仅用于均线计算，不能当作所选区间内的行情事件。
不要分析基本面、新闻、公司公告或宏观因素；不要编造未提供的指标、价位、原因或数据。
区间涨幅、均线和回撤等数值应直接依据工具结果。每条 key_points 都必须引用工具返回的 evidence_ids。
当区间数据不足以支持判断时，降低 confidence 并在 data_gaps 中说明。
不要给出买入、卖出、仓位或目标价建议。
调用工具拿到数据后，直接输出最终结果；不要输出分析过程、进度说明或"接下来我将…"这类文字。
最终只返回一个 JSON 对象，字段为：
stance (bullish/neutral/bearish), conclusion (string), key_points (array of {text, evidence_ids}),
confidence (0 到 1), data_gaps (string array)。"""


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in ("text", "output_text")
        ]
        return "\n".join(part for part in parts if part).strip()
    return ""


def _extract_json_object(text: str) -> dict | None:
    """从夹带解释文字或代码块的回复里取出第一个完整 JSON 对象。"""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _parse_report(content: Any) -> MarketAnalystReport:
    text = _content_text(content)
    if not text:
        raise LLMCallError("模型没有返回行情分析报告文本。")
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # 小模型常在 JSON 前后附带说明文字，不能只认纯 JSON
        payload = _extract_json_object(text)
        if payload is None:
            logger.warning("模型输出无法解析为 JSON：%s", text[:300])
            raise LLMCallError(
                "模型输出不是约定的 JSON 格式，请检查所选模型的结构化输出能力。"
            ) from None
    try:
        return MarketAnalystReport.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("模型 JSON 字段不符合结构：%s", str(payload)[:300])
        raise LLMCallError("模型 JSON 字段不符合行情分析报告结构。") from exc


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
    allowed_evidence_ids = {item.evidence_id for item in all_evidence}

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
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请分析下面任务范围内的 K 线。先使用工具读取统计，再按需要查询 K 线细节。\n"
            + json.dumps(task_summary, ensure_ascii=False),
        },
    ]

    used_tools: set[str] = set()
    total_tool_calls = 0
    tool_rounds = 0
    json_repairs = 0
    while tool_rounds < MAX_TOOL_ROUNDS:
        # 统一用 auto：智谱等提供商只支持 auto，且 system prompt 已要求先调统计工具，
        # 下面还会校验 get_window_statistics 是否真的调用过，未调用则拒收报告
        choice = request_chat_completion(
            settings,
            messages,
            tool_schemas,
            "auto",
        )
        tool_calls = choice.get("tool_calls") or []
        if not tool_calls:
            if "get_window_statistics" not in used_tools:
                raise LLMCallError("模型未使用行情统计工具，未采纳其报告。")
            try:
                report = _parse_report(choice.get("content"))
            except LLMCallError:
                # 小模型常在工具调用后先输出一段分析文字或后续计划，
                # 此时追加一轮，明确要求只返回 JSON；仍不合格才判定失败
                if json_repairs >= MAX_JSON_REPAIRS:
                    raise
                json_repairs += 1
                logger.warning("模型未返回 JSON，追加一次格式纠正（第 %s 次）", json_repairs)
                messages.append({"role": "assistant", "content": choice.get("content") or ""})
                messages.append({"role": "user", "content": _JSON_REPAIR_PROMPT})
                continue
            invalid_ids = {
                evidence_id
                for point in report.key_points
                for evidence_id in point.evidence_ids
                if evidence_id not in allowed_evidence_ids
            }
            if invalid_ids:
                raise LLMCallError("模型引用了本次任务中不存在的证据，报告未通过校验。")
            cited_ids = {evidence_id for point in report.key_points for evidence_id in point.evidence_ids}
            cited_evidence = [item for item in all_evidence if item.evidence_id in cited_ids]
            return report, settings.model_name, cited_evidence

        tool_rounds += 1
        total_tool_calls += len(tool_calls)
        if total_tool_calls > MAX_TOOL_CALLS:
            raise LLMCallError("模型工具调用次数超过限制，分析已停止。")
        messages.append(
            {
                "role": "assistant",
                "content": choice.get("content"),
                "tool_calls": tool_calls,
            }
        )
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            name = function.get("name")
            call_id = tool_call.get("id")
            try:
                arguments = function.get("arguments") or "{}"
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("工具参数必须是 JSON 对象")
                result = execute_tool(name, arguments)
                used_tools.add(name)
                tool_result = {"ok": True, "result": result}
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                tool_result = {"ok": False, "error": str(exc)}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name or "unknown",
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )

    raise LLMCallError("模型在工具调用次数限制内没有完成行情分析。")


def market_analyst_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph 可调用的行情分析节点，返回结构化结论和引用证据。"""
    report, model_name, cited_evidence = run_market_analyst(state)
    return {
        "market_report": report,
        "evidence": list(state.get("evidence", []))
        + [
            item
            for item in cited_evidence
            if item.evidence_id not in {e.evidence_id for e in state.get("evidence", [])}
        ],
        "sender": "market_analyst",
        "current_stage": AnalysisStage.ANALYST,
        "market_model_name": model_name,
    }
