"""分析任务的数据接入与分析工作流接口。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from agents.analysis_context_builder import build_initial_context
from agents.llm_provider_client import (
    LLMCallError,
    LLMConfigurationError,
    UnknownProviderError,
    available_providers,
    default_provider_key,
    load_llm_settings,
)
from agents.workflow import get_analysis_workflow, initial_workflow_state
from app.presenters.analysis_response_builder import (
    build_ingestion_response,
    build_run_response,
)
from app.schemas.analysis_schemas import (
    AnalysisRunResponse,
    AnalysisStage,
    AnalysisTaskRequest,
    DataIngestionResponse,
    LLMProviderOption,
    MarketAnalysisResponse,
)

logger = logging.getLogger("finagent.analysis.routes")
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _run_workflow(
    request: AnalysisTaskRequest,
    analysts: tuple[str, ...],
    include_decision: bool,
) -> dict:
    """同步执行一次工作流（由 asyncio.to_thread 调用）。"""
    # 先校验提供商配置，避免把配置错误带进图里再暴露成通用异常
    load_llm_settings(request.provider)
    return get_analysis_workflow(analysts, include_decision).invoke(
        initial_workflow_state(request)
    )


async def _execute_workflow(
    request: AnalysisTaskRequest,
    analysts: tuple[str, ...] = ("market", "fundamental", "news"),
    include_decision: bool = True,
) -> dict:
    """执行工作流并把各类失败映射成对应的 HTTP 状态码。"""
    try:
        return await asyncio.to_thread(_run_workflow, request, analysts, include_decision)
    except UnknownProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except LLMCallError as e:
        logger.warning("%s 分析工作流失败：%s", request.stock_code, e)
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("%s 分析工作流执行失败", request.stock_code)
        raise HTTPException(status_code=502, detail="分析执行失败，请查看后端日志。") from e


@router.post("/ingest", response_model=DataIngestionResponse)
async def ingest_data(request: AnalysisTaskRequest):
    """按前端选定的周期和日期区间执行真实数据接入。"""
    try:
        state = await asyncio.to_thread(
            build_initial_context,
            request,
        )
        return build_ingestion_response(request, state)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("数据接入失败：%s", request.stock_code)
        raise HTTPException(status_code=502, detail=f"数据接入失败：{e}") from e


@router.get("/providers", response_model=list[LLMProviderOption])
async def list_llm_providers():
    """列出已配置 API Key 的模型提供商，供前端选择。"""
    default_key = default_provider_key()
    return [
        LLMProviderOption(**item, is_default=item["key"] == default_key)
        for item in available_providers()
    ]


@router.post("/market", response_model=MarketAnalysisResponse)
async def analyze_market(request: AnalysisTaskRequest):
    """只运行行情分析师节点，返回该阶段的结论（前端当前调用路径）。"""
    state = await _execute_workflow(request, analysts=("market",), include_decision=False)
    evidence = list(state.get("market_report_evidence") or [])
    kline = state.get("kline_data") or {}
    return MarketAnalysisResponse(
        stock_code=request.stock_code,
        stock_name=kline.get("name"),
        period=request.period,
        actual_start_date=state["actual_start_date"],
        actual_end_date=state["actual_end_date"],
        provider=state.get("market_provider") or request.provider or "",
        model_name=state.get("market_model_name") or "",
        report=state["market_report"],
        evidence=evidence,
        limitations=list(dict.fromkeys(
            limitation
            for item in evidence
            for limitation in item.limitations
        )),
    )


@router.post("/run", response_model=AnalysisRunResponse)
async def run_analysis(request: AnalysisTaskRequest):
    """同步执行完整分析工作流，返回各阶段结论（保留给脚本和调试使用）。"""
    state = await _execute_workflow(request)
    return build_run_response(request, state, state.get("task_id") or "")
