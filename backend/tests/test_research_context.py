"""下游角色输入整理：证据目录、引用过滤与分析摘要。"""

from datetime import date

from agents.research_context import (
    allowed_evidence_ids,
    build_analysis_summary,
    evidence_catalog,
    sanitize_evidence_ids,
)
from app.schemas.analysis_schemas import (
    AnalystFinding,
    EvidenceItem,
    MarketAnalysisPoint,
    MarketAnalystReport,
)


def _evidence(evidence_id, category="market", limitations=None):
    return EvidenceItem(
        evidence_id=evidence_id,
        category=category,
        source="测试来源",
        summary="证据摘要",
        observed_at=date(2026, 9, 30),
        data={},
        limitations=limitations or [],
    )


def test_sanitize_evidence_ids_drops_unknown_and_duplicates():
    assert sanitize_evidence_ids(["a", "b", "a", "c"], {"a", "b"}) == ["a", "b"]


def test_evidence_catalog_keeps_citable_fields():
    catalog = evidence_catalog([_evidence("e1")])
    assert catalog == [
        {
            "id": "e1",
            "category": "market",
            "source": "测试来源",
            "observed_at": "2026-09-30",
            "summary": "证据摘要",
        }
    ]


def test_build_analysis_summary_includes_reports_and_limitations():
    market = MarketAnalystReport(
        stance="bullish",
        conclusion="区间上涨",
        key_points=[MarketAnalysisPoint(text="涨幅 3%", evidence_ids=["e1"])],
        confidence=0.8,
        data_gaps=[],
    )
    fundamental = AnalystFinding(
        analyst="fundamental",
        stance="neutral",
        conclusion="盈利稳健",
        key_points=["ROE 高"],
        evidence_ids=["e2"],
        confidence=0.5,
    )
    state = {
        "stock_code": "600519",
        "analysis_period": "daily",
        "kline_data": {
            "name": "贵州茅台",
            "actual_start_date": "2026-09-01",
            "actual_end_date": "2026-09-30",
        },
        "market_report": market,
        "fundamentals_report": fundamental,
        "evidence": [
            _evidence("e1"),
            _evidence("e2", "fundamental", ["缺少季报"]),
            _evidence("e3", "news"),
        ],
    }

    summary = build_analysis_summary(state)

    assert summary["stock_code"] == "600519"
    assert summary["analysis_range"] == {"start": "2026-09-01", "end": "2026-09-30"}
    assert summary["analyst_reports"]["market"]["stance"] == "bullish"
    assert summary["analyst_reports"]["fundamental"]["conclusion"] == "盈利稳健"
    assert summary["analyst_reports"]["news"] is None
    assert [item["id"] for item in summary["evidence"]] == ["e1", "e2", "e3"]
    assert summary["data_limitations"] == ["缺少季报"]
    assert allowed_evidence_ids(state) == {"e1", "e2", "e3"}
