"""基本面分析师可调用的工具：当前估值指标或按公告日回溯的定期财报。"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from app.schemas.analysis_schemas import EvidenceItem

_METRIC_FIELDS = (
    "industry",
    "marketCap",
    "pe",
    "pb",
    "roe",
    "revGrowth",
    "profitGrowth",
    "margin",
    "dividendYield",
)


def _fundamental_evidence(context: Mapping[str, Any]) -> EvidenceItem:
    evidence = next(
        (
            item
            for item in context.get("evidence", [])
            if getattr(item, "category", None) == "fundamental"
        ),
        None,
    )
    if evidence is None:
        raise ValueError("分析上下文缺少基本面证据")
    return evidence


def build_fundamental_tools(
    context: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Callable[[str, dict[str, Any]], dict[str, Any]], str]:
    """按当前/历史两种模式提供工具，返回 (工具定义, 执行函数, 必需工具名)。"""
    data = context.get("fundamentals_data") or {}
    evidence = _fundamental_evidence(context)
    historical = "baseline" in data or "reports_in_range" in data

    if historical:
        baseline = data.get("baseline")
        reports = list(data.get("reports_in_range") or [])
        limitations = list(data.get("limitations") or [])
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "get_financial_reports",
                    "description": (
                        "读取所选区间内披露的定期财报，以及区间开始前已披露的基线财报，"
                        "每条包含报告期与公告日期。"
                    ),
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            }
        ]

        def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            if name != "get_financial_reports":
                raise ValueError(f"未知工具：{name}")
            return {
                "baseline": baseline,
                "reports_in_range": reports,
                "limitations": limitations,
                "evidence_ids": [evidence.evidence_id],
            }

        return schemas, execute, "get_financial_reports"

    metrics = {key: data.get(key) for key in _METRIC_FIELDS}
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "get_fundamental_metrics",
                "description": (
                    "读取当前可用的行业、估值、盈利能力、成长性与股息率指标。"
                    "这些是当前快照，不能代表过去某个日期当时的公开数据。"
                ),
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }
    ]

    def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != "get_fundamental_metrics":
            raise ValueError(f"未知工具：{name}")
        return {
            "metrics": metrics,
            "evidence_ids": [evidence.evidence_id],
        }

    return schemas, execute, "get_fundamental_metrics"
