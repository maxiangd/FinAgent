"""把领域异常统一映射成 HTTP 响应，避免每个路由重复 try/except。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agents.llm_provider_client import (
    LLMCallError,
    LLMConfigurationError,
    UnknownProviderError,
)

logger = logging.getLogger("finagent.errors")

# 按具体类型注册：子类在前，Starlette 按 MRO 匹配最近的处理器
ERROR_STATUS = {
    UnknownProviderError: 400,
    LLMConfigurationError: 503,
    LLMCallError: 502,
    LookupError: 404,
    ValueError: 400,
}


def register_exception_handlers(app: FastAPI) -> None:
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        status = next(
            (code for error_type, code in ERROR_STATUS.items() if isinstance(exc, error_type)),
            400,
        )
        if isinstance(exc, LLMCallError):
            logger.warning("%s %s 失败：%s", request.method, request.url.path, exc)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    for error_type in ERROR_STATUS:
        app.add_exception_handler(error_type, handle)
