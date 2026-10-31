"""新闻情绪分析师可调用的工具：新闻与公司公告的覆盖情况和条目。"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from app.schemas.analysis_schemas import EvidenceItem

MAX_NEWS_ITEMS = 40


def _news_evidence(context: Mapping[str, Any]) -> EvidenceItem:
    evidence = next(
        (
            item
            for item in context.get("evidence", [])
            if getattr(item, "category", None) == "news"
        ),
        None,
    )
    if evidence is None:
        raise ValueError("分析上下文缺少新闻证据")
    return evidence


def _item_date(item: Mapping[str, Any]) -> str:
    raw = item.get("published_at") or item.get("time") or ""
    return str(raw)[:10]


def build_news_tools(
    context: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Callable[[str, dict[str, Any]], dict[str, Any]], str]:
    """返回 (工具定义, 执行函数, 必需工具名)。"""
    data = context.get("news_data") or {}
    evidence = _news_evidence(context)
    items = [item for item in (data.get("items") or []) if isinstance(item, dict)]
    limitations = list(data.get("limitations") or [])

    news_count = sum(1 for item in items if (item.get("kind") or "news") == "news")
    announcement_count = len(items) - news_count
    dated = sorted({_item_date(item) for item in items if _item_date(item)})

    schemas = [
        {
            "type": "function",
            "function": {
                "name": "get_news_overview",
                "description": "读取所选区间内新闻与公司公告的数量、覆盖日期范围和数据限制说明。",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_news_items",
                "description": (
                    "读取具体的新闻或公告标题、发布日期和来源。可按 kind 过滤，最多返回 40 条。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["news", "company_announcement"],
                            "description": "可选：只看媒体新闻或只看公司公告",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_NEWS_ITEMS,
                            "description": "最多返回条数，默认 20",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
    ]

    def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_news_overview":
            return {
                "total": len(items),
                "media_news_count": news_count,
                "company_announcement_count": announcement_count,
                "coverage_start": dated[0] if dated else None,
                "coverage_end": dated[-1] if dated else None,
                "limitations": limitations,
                "evidence_ids": [evidence.evidence_id],
            }
        if name == "get_news_items":
            kind = arguments.get("kind")
            if kind not in (None, "news", "company_announcement"):
                raise ValueError("kind 只能是 news 或 company_announcement")
            try:
                limit = int(arguments.get("limit", 20))
            except (TypeError, ValueError) as exc:
                raise ValueError("limit 必须是整数") from exc
            if not 1 <= limit <= MAX_NEWS_ITEMS:
                raise ValueError(f"limit 必须在 1 到 {MAX_NEWS_ITEMS} 之间")
            selected = [
                item
                for item in items
                if kind is None or (item.get("kind") or "news") == kind
            ][:limit]
            return {
                "items": [
                    {
                        "title": str(item.get("title") or "")[:200],
                        "published_at": _item_date(item) or None,
                        "source": item.get("source"),
                        "kind": item.get("kind") or "news",
                    }
                    for item in selected
                ],
                "returned": len(selected),
                "evidence_ids": [evidence.evidence_id],
            }
        raise ValueError(f"未知工具：{name}")

    return schemas, execute, "get_news_overview"
