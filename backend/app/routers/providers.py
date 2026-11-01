"""模型提供商查询：返回已配置 API Key 的提供商，供前端选择。"""

from __future__ import annotations

from fastapi import APIRouter

from agents.llm_provider_client import available_providers, default_provider_key
from app.schemas.analysis_schemas import LLMProviderOption

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/providers", response_model=list[LLMProviderOption])
async def list_llm_providers():
    """列出已配置 API Key 的模型提供商，不返回密钥。"""
    default_key = default_provider_key()
    return [
        LLMProviderOption(**item, is_default=item["key"] == default_key)
        for item in available_providers()
    ]
