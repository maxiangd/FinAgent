"""分析任务的数据接入预览接口。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from agents.analysts.market_analyst_agent import run_market_analyst
from agents.analysis_context_builder import build_initial_context
from agents.llm_provider_client import (
    LLMCallError,
    LLMConfigurationError,
    UnknownProviderError,
    available_providers,
    default_provider_key,
    load_llm_settings,
)
from app.presenters.analysis_response_builder import build_ingestion_response
from app.schemas.analysis_schemas import (
    AnalysisTaskRequest,
    DataIngestionResponse,
    LLMProviderOption,
    MarketAnalysisResponse,
)

logger = logging.getLogger("finagent.analysis.routes")
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


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
    """按所选周期和区间取数，并运行一次真实行情分析师。"""
    try:
        settings = load_llm_settings(request.provider)
        context = await asyncio.to_thread(build_initial_context, request)
        report, model_name, evidence = await asyncio.to_thread(
            run_market_analyst,
            context,
            settings,
        )
        limitations = list(dict.fromkeys(
            limitation
            for item in evidence
            for limitation in item.limitations
        ))
        kline = context.get("kline_data") or {}
        return MarketAnalysisResponse(
            stock_code=request.stock_code,
            stock_name=kline.get("name"),
            period=request.period,
            actual_start_date=context["actual_start_date"],
            actual_end_date=context["actual_end_date"],
            provider=settings.provider,
            model_name=model_name,
            report=report,
            evidence=evidence,
            limitations=limitations,
        )
    except UnknownProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except LLMCallError as e:
        logger.warning("%s 行情分析师调用失败：%s", request.stock_code, e)
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("%s 行情分析师执行失败", request.stock_code)
        raise HTTPException(status_code=502, detail="行情分析师执行失败，请查看后端日志。") from e
