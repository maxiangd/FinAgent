"""Swagger UI 文档页：静态资源走国内镜像。

FastAPI 默认从 cdn.jsdelivr.net 加载 Swagger UI，该域名在部分网络下不可达，
表现为 /docs 白屏。这里改用 npmmirror（淘宝 NPM 镜像）。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html

SWAGGER_UI_VERSION = "5.17.14"
_ASSET_BASE = f"https://registry.npmmirror.com/swagger-ui-dist/{SWAGGER_UI_VERSION}/files"


def setup_docs(app: FastAPI) -> None:
    @app.get("/docs", include_in_schema=False)
    async def swagger_ui():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} · Swagger UI",
            swagger_js_url=f"{_ASSET_BASE}/swagger-ui-bundle.js",
            swagger_css_url=f"{_ASSET_BASE}/swagger-ui.css",
            swagger_favicon_url=f"{_ASSET_BASE}/favicon-32x32.png",
        )
