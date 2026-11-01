"""批量评测：固定样例跑完整分析链路，统计成功率、耗时、证据覆盖率与调用成本。

用法（在 backend 目录）：
    python scripts/run_evaluation.py --limit 2
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from agents.llm_provider_client import get_call_stats, reset_call_stats
from app.schemas.analysis_schemas import AnalysisTaskRequest, TaskStatus
from app.task_manager import task_manager

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "evaluation"

# 固定样例：股票 × 周期 × 区间
SAMPLES = [
    ("600519", "daily", "2026-09-01", "2026-09-30"),
    ("600519", "weekly", "2026-01-05", "2026-10-30"),
    ("000001", "daily", "2026-06-01", "2026-09-30"),
    ("300750", "daily", "2026-03-02", "2026-06-30"),
]

STAGES = ("ingest", "analyst", "debate", "trader", "risk", "pm")
POLL_SECONDS = 3
TIMEOUT_SECONDS = 15 * 60


def stage_durations(events) -> dict[str, float]:
    """按 stage_started / stage_completed 事件时间戳计算各阶段耗时。"""
    durations: dict[str, float] = {}
    started: dict[str, datetime] = {}
    for event in events:
        stage = event.stage.value if event.stage else None
        if not stage:
            continue
        if event.event_type.value == "stage_started":
            started[stage] = event.created_at
        elif event.event_type.value == "stage_completed" and stage in started:
            durations[stage] = round((event.created_at - started.pop(stage)).total_seconds(), 1)
    return durations


def evidence_metrics(result) -> tuple[float, int, int]:
    """统计结论是否引用了证据，以及引用了多少不存在的证据 ID。"""
    units = 0
    cited = 0
    invalid = 0
    valid_ids = {item.evidence_id for item in result.evidence}

    def count(ids) -> None:
        nonlocal units, cited, invalid
        units += 1
        if ids:
            cited += 1
            invalid += sum(1 for evidence_id in ids if evidence_id not in valid_ids)

    for point in result.market_report.key_points:
        count(point.evidence_ids)
    for finding in (result.fundamental_report, result.news_report):
        if finding is not None:
            count(finding.evidence_ids)
    for turn in result.debate_turns:
        count(turn.evidence_ids)
    if result.trade_proposal is not None:
        count(result.trade_proposal.evidence_ids)
    if result.pm_decision is not None:
        count(result.pm_decision.evidence_ids)

    coverage = round(cited / units, 3) if units else 0.0
    return coverage, invalid, units


def run_sample(code: str, period: str, start: str, end: str) -> dict:
    request = AnalysisTaskRequest(
        stock_code=code, period=period, start_date=start, end_date=end
    )
    reset_call_stats()
    started = time.time()
    record = task_manager.create_task(request)

    while record.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
        if time.time() - started > TIMEOUT_SECONDS:
            task_manager.cancel_task(record.task_id)
            break
        time.sleep(POLL_SECONDS)

    duration = round(time.time() - started, 1)
    stats = get_call_stats()
    row: dict[str, object] = {
        "sample": f"{code}-{period}-{start}-{end}",
        "stock_code": code,
        "period": period,
        "start_date": start,
        "end_date": end,
        "status": record.status.value,
        "duration_s": duration,
        "llm_calls": stats["calls"],
        "prompt_tokens": stats["prompt_tokens"],
        "completion_tokens": stats["completion_tokens"],
        "error_code": record.error.code if record.error else "",
        "error_message": (record.error.message[:120] if record.error else ""),
    }
    durations = stage_durations(record.snapshot_events())
    for stage in STAGES:
        row[f"{stage}_s"] = durations.get(stage, "")

    result = record.result
    if result is not None:
        coverage, invalid, units = evidence_metrics(result)
        row.update(
            {
                "debate_turns": len(result.debate_turns),
                "risk_reviews": len(result.risk_reviews),
                "pm_action": result.pm_decision.action if result.pm_decision else "",
                "pm_confidence": result.pm_decision.confidence if result.pm_decision else "",
                "evidence_units": units,
                "evidence_coverage": coverage,
                "invalid_citations": invalid,
                "task_id": result.task_id,
            }
        )
    return row


def build_summary(rows: list[dict], timestamp: str) -> str:
    total = len(rows)
    completed = [row for row in rows if row["status"] == "completed"]
    lines = [f"# 分析链路评测（{timestamp}）", ""]
    rate = len(completed) / total * 100 if total else 0.0
    lines.append(f"- 样例数：{total}，成功：{len(completed)}，成功率：{rate:.1f}%")

    if completed:
        def average(key: str) -> float:
            return sum(float(row[key]) for row in completed) / len(completed)

        lines += [
            f"- 平均耗时：{average('duration_s'):.1f}s",
            (
                f"- 平均模型调用：{average('llm_calls'):.1f} 次"
                f"（prompt {average('prompt_tokens'):.0f} / completion {average('completion_tokens'):.0f} tokens）"
            ),
            f"- 平均证据引用覆盖率：{average('evidence_coverage') * 100:.1f}%",
            f"- 无效引用合计：{sum(int(row['invalid_citations']) for row in completed)}",
            "",
            "| 阶段 | 平均耗时(s) |",
            "| --- | --- |",
        ]
        for stage in STAGES:
            values = [
                float(row[f"{stage}_s"])
                for row in completed
                if row.get(f"{stage}_s") not in ("", None)
            ]
            if values:
                lines.append(f"| {stage} | {sum(values) / len(values):.1f} |")

        actions: dict[str, int] = {}
        for row in completed:
            action = str(row.get("pm_action") or "-")
            actions[action] = actions.get(action, 0) + 1
        lines += ["", "PM 决策分布：" + "，".join(f"{key} {value}" for key, value in actions.items())]

    failed = [row for row in rows if row["status"] != "completed"]
    if failed:
        lines += ["", "失败样例："]
        for row in failed:
            lines.append(
                f"- {row['sample']}：{row['status']} / {row['error_code']} {row['error_message']}"
            )

    lines += ["", "说明：证据引用覆盖率 = 引用了至少一条有效证据的结论单元 / 全部结论单元。"]
    return "\n".join(lines) + "\n"


def write_outputs(rows: list[dict], timestamp: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    csv_path = OUTPUT_DIR / f"results-{timestamp}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = build_summary(rows, timestamp)
    summary_path = OUTPUT_DIR / f"summary-{timestamp}.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"\nCSV: {csv_path}")
    print(f"汇总: {summary_path}")
    print(summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=len(SAMPLES))
    args = parser.parse_args()

    samples = SAMPLES[: max(1, args.limit)]
    rows = []
    for index, sample in enumerate(samples, start=1):
        code, period, start, end = sample
        print(f"[{index}/{len(samples)}] {code} {period} {start}~{end}", flush=True)
        row = run_sample(code, period, start, end)
        print(f"  -> {row['status']} {row['duration_s']}s calls={row['llm_calls']}", flush=True)
        rows.append(row)

    write_outputs(rows, datetime.now().strftime("%Y%m%d-%H%M%S"))


if __name__ == "__main__":
    main()
