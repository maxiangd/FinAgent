"""分析师共用的工具调用运行时：多轮工具、证据校验与 JSON 格式纠正。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from agents.llm_provider_client import LLMCallError, LLMSettings, request_chat_completion
from app.schemas.analysis_schemas import EvidenceItem

logger = logging.getLogger("finagent.analyst.runtime")

MAX_TOOL_ROUNDS = 5
MAX_TOOL_CALLS = 8
MAX_JSON_REPAIRS = 2

JSON_REPAIR_PROMPT = (
    "现在直接输出最终结论：只返回一个 JSON 对象，不要输出解释、标题、列表、进度说明或后续计划。"
)

ReportT = TypeVar("ReportT", bound=BaseModel)


def content_text(content: Any) -> str:
    """把模型返回的 content 统一成纯文本。"""
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


def extract_json_object(text: str) -> dict | None:
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


def parse_json_payload(content: Any) -> dict[str, Any]:
    """把模型输出解析成 JSON 对象（不做结构校验）。"""
    text = content_text(content)
    if not text:
        raise LLMCallError("模型没有返回分析报告文本。")
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # 小模型常在 JSON 前后附带说明文字，不能只认纯 JSON
        payload = extract_json_object(text)
        if payload is None:
            logger.warning("模型输出无法解析为 JSON：%s", text[:300])
            raise LLMCallError(
                "模型输出不是约定的 JSON 格式，请检查所选模型的结构化输出能力。"
            ) from None
    if not isinstance(payload, dict):
        raise LLMCallError("模型输出的 JSON 不是对象。")
    return payload


def _validation_detail(exc: Exception) -> str:
    """把 pydantic 校验错误压成一行可读提示。"""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return ""
    try:
        return "；".join(
            f"{'.'.join(str(part) for part in error.get('loc', []))}: {error.get('msg', '')}"
            for error in errors()[:3]
        )
    except Exception:  # noqa: BLE001
        return ""


def validate_report(payload: dict[str, Any], model_cls: type[ReportT]) -> ReportT:
    """按报告模型校验字段；失败时把具体字段错误带进消息。"""
    try:
        return model_cls.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("模型 JSON 字段不符合结构：%s", str(payload)[:300])
        detail = _validation_detail(exc)
        raise LLMCallError(
            f"模型 JSON 字段不符合约定的报告结构{'：' + detail if detail else ''}"
        ) from exc


def parse_json_report(content: Any, model_cls: type[ReportT]) -> ReportT:
    """把模型输出解析并校验成指定的报告模型。"""
    return validate_report(parse_json_payload(content), model_cls)


def run_structured_completion(
    *,
    settings: LLMSettings,
    system_prompt: str,
    payload: dict[str, Any],
    model_cls: type[ReportT],
    max_repairs: int = 2,
) -> ReportT:
    """单次结构化调用：不使用工具，要求模型直接返回约定的 JSON。"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    repairs = 0
    while True:
        choice = request_chat_completion(settings, messages, [], "auto")
        try:
            return parse_json_report(choice.get("content"), model_cls)
        except LLMCallError as exc:
            if repairs >= max_repairs:
                raise
            repairs += 1
            logger.warning("模型未返回合格 JSON，追加一次格式纠正（第 %s 次）", repairs)
            messages.append({"role": "assistant", "content": choice.get("content") or ""})
            messages.append(
                {
                    "role": "user",
                    "content": f"上一轮输出不符合要求：{exc}。{JSON_REPAIR_PROMPT}",
                }
            )


def run_tool_agent(
    *,
    settings: LLMSettings,
    system_prompt: str,
    task_summary: dict[str, Any],
    instruction: str,
    tool_schemas: list[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    required_tool: str,
    parse_report: Callable[[Any], ReportT],
    citation_ids: Callable[[ReportT], set[str]],
    candidate_evidence: list[EvidenceItem],
) -> tuple[ReportT, list[EvidenceItem]]:
    """跑完一次「模型 ↔ 工具」对话，返回结构化报告和它引用的证据。"""
    allowed_evidence_ids = {item.evidence_id for item in candidate_evidence}
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": instruction + "\n" + json.dumps(task_summary, ensure_ascii=False),
        },
    ]

    used_tools: set[str] = set()
    total_tool_calls = 0
    tool_rounds = 0
    json_repairs = 0

    while tool_rounds < MAX_TOOL_ROUNDS:
        # 统一用 auto：智谱等提供商只支持 auto；required_tool 由下面的校验保证
        choice = request_chat_completion(settings, messages, tool_schemas, "auto")
        tool_calls = choice.get("tool_calls") or []

        if not tool_calls:
            if required_tool not in used_tools:
                raise LLMCallError(f"模型未使用 {required_tool} 工具，未采纳其报告。")
            try:
                report = parse_report(choice.get("content"))
            except LLMCallError as exc:
                # 小模型常在工具调用后先输出一段分析文字或后续计划，
                # 此时追加一轮，明确要求只返回 JSON；仍不合格才判定失败
                if json_repairs >= MAX_JSON_REPAIRS:
                    raise
                json_repairs += 1
                logger.warning("模型未返回合格 JSON，追加一次格式纠正（第 %s 次）", json_repairs)
                messages.append({"role": "assistant", "content": choice.get("content") or ""})
                messages.append(
                    {
                        "role": "user",
                        "content": f"上一轮输出不符合要求：{exc}。{JSON_REPAIR_PROMPT}",
                    }
                )
                continue

            invalid_ids = citation_ids(report) - allowed_evidence_ids
            if invalid_ids:
                raise LLMCallError("模型引用了本次任务中不存在的证据，报告未通过校验。")
            cited = [item for item in candidate_evidence if item.evidence_id in citation_ids(report)]
            return report, cited

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

    raise LLMCallError("模型在工具调用次数限制内没有完成分析。")
