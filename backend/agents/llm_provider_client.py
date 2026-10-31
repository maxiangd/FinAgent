"""OpenAI 兼容接口客户端；仅从后端环境变量读取模型配置。"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from config.settings import get_env_str


class LLMConfigurationError(RuntimeError):
    """模型服务配置缺失或无效。"""


class UnknownProviderError(LLMConfigurationError):
    """请求了未定义的模型提供商。"""


class LLMCallError(RuntimeError):
    """模型服务请求或响应失败。"""


@dataclass(frozen=True)
class LLMProviderSpec:
    """一个可选提供商的默认地址与模型，可被环境变量覆盖。"""

    key: str
    label: str
    base_url: str
    model_name: str


PROVIDER_SPECS = (
    # glm-4.7-flash 更新但高峰期常 429；glm-4-flash-250414 同为免费且更稳，可用 LLM_ZHIPU_MODEL 切换
    LLMProviderSpec("zhipu", "智谱 GLM（免费）", "https://open.bigmodel.cn/api/paas/v4", "glm-4.7-flash"),
    LLMProviderSpec("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    LLMProviderSpec(
        "qwen",
        "通义千问",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
    ),
)


@dataclass(frozen=True)
class LLMSettings:
    """单次模型调用需要的连接设置。"""

    provider: str
    label: str
    base_url: str
    api_key: str
    model_name: str
    timeout_seconds: int


def _providerget_env_str(key: str, field: str) -> str:
    return get_env_str(f"LLM_{key.upper()}_{field}")


def _timeout_seconds() -> int:
    raw = get_env_str("LLM_TIMEOUT_SECONDS") or "90"
    try:
        timeout = int(raw)
    except ValueError as exc:
        raise LLMConfigurationError("LLM_TIMEOUT_SECONDS 必须是整数") from exc
    if not 5 <= timeout <= 300:
        raise LLMConfigurationError("LLM_TIMEOUT_SECONDS 必须在 5 到 300 秒之间")
    return timeout


def available_providers() -> list[dict]:
    """返回已配置 API Key 的提供商（不含密钥），供前端选择。"""
    providers = []
    for spec in PROVIDER_SPECS:
        if not _providerget_env_str(spec.key, "API_KEY"):
            continue
        providers.append(
            {
                "key": spec.key,
                "label": spec.label,
                "model": _providerget_env_str(spec.key, "MODEL") or spec.model_name,
            }
        )
    return providers


def default_provider_key() -> str | None:
    """默认提供商：LLM_DEFAULT_PROVIDER 指定的优先，否则取第一个已配置的。"""
    configured = [item["key"] for item in available_providers()]
    if not configured:
        return None
    preferred = get_env_str("LLM_DEFAULT_PROVIDER").lower()
    return preferred if preferred in configured else configured[0]


def load_llm_settings(provider: str | None = None) -> LLMSettings:
    """读取指定提供商的配置；不传时使用默认提供商，不返回或记录 API 密钥。"""
    specs = {spec.key: spec for spec in PROVIDER_SPECS}
    requested = (provider or "").strip().lower()
    if requested and requested not in specs:
        raise UnknownProviderError(f"未知的模型提供商：{requested}")
    key = requested or default_provider_key()
    if not key:
        raise LLMConfigurationError(
            "尚未配置模型服务。请在后端 .env 中至少填写一个提供商的 API Key，"
            "例如 LLM_ZHIPU_API_KEY（智谱，免费）。"
        )
    api_key = _providerget_env_str(key, "API_KEY")
    if not api_key:
        raise LLMConfigurationError(
            f"未配置 {specs[key].label} 的 API Key，请在 .env 中填写 LLM_{key.upper()}_API_KEY。"
        )
    return LLMSettings(
        provider=key,
        label=specs[key].label,
        base_url=(_providerget_env_str(key, "BASE_URL") or specs[key].base_url).rstrip("/"),
        api_key=api_key,
        model_name=_providerget_env_str(key, "MODEL") or specs[key].model_name,
        timeout_seconds=_timeout_seconds(),
    )


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _retry_attempts() -> int:
    try:
        attempts = int(get_env_str("LLM_MAX_ATTEMPTS") or "3")
    except ValueError:
        return 3
    return min(max(attempts, 1), 5)


def _retry_delay(response: requests.Response, attempt: int) -> float:
    """优先用服务端的 Retry-After，否则按 3s、6s… 指数退避。"""
    header = response.headers.get("Retry-After", "")
    try:
        return min(max(float(header), 1.0), 30.0)
    except ValueError:
        return min(3.0 * (2**attempt), 20.0)


def _error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict):
        error = payload.get("error") or payload.get("message") or payload
        return str(error)[:200]
    return str(payload)[:200]


def _post_chat(url: str, settings: LLMSettings, body: dict) -> requests.Response:
    """发送请求；429/5xx 按退避重试，返回最后一次响应。"""
    attempts = _retry_attempts()
    response: requests.Response | None = None
    for attempt in range(attempts):
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=settings.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise LLMCallError("模型请求超时；可以稍后重试或调高 LLM_TIMEOUT_SECONDS。") from exc
        except requests.RequestException as exc:
            raise LLMCallError(f"无法连接模型服务：{type(exc).__name__}。请检查地址和网络。") from exc
        if response.status_code not in RETRYABLE_STATUS or attempt == attempts - 1:
            return response
        time.sleep(_retry_delay(response, attempt))
    assert response is not None
    return response


def request_chat_completion(
    settings: LLMSettings,
    messages: list[dict],
    tools: list[dict],
    tool_choice: str,
) -> dict:
    """调用支持工具调用的 OpenAI 兼容 Chat Completions 接口。"""
    url = f"{settings.base_url}/chat/completions"
    response = _post_chat(
        url,
        settings,
        {
            "model": settings.model_name,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        },
    )

    if response.status_code == 429:
        raise LLMCallError(
            f"{settings.label} 触发限流（HTTP 429，已重试 {_retry_attempts()} 次）："
            f"{_error_detail(response)}。免费模型高峰期常见，可稍后再试，"
            "或在页面上换用其他模型提供商。"
        )
    if response.status_code in (401, 403):
        raise LLMCallError(
            f"{settings.label} 鉴权失败，请检查 .env 中的 LLM_{settings.provider.upper()}_API_KEY。"
        )
    if response.status_code == 404:
        raise LLMCallError(
            f"{settings.label} 返回 404，请检查 LLM_{settings.provider.upper()}_BASE_URL 和 "
            f"LLM_{settings.provider.upper()}_MODEL（当前模型 {settings.model_name}）。"
        )
    if not response.ok:
        raise LLMCallError(
            f"{settings.label} 返回 HTTP {response.status_code}。{_error_detail(response)}".strip()
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMCallError("模型服务返回的内容不是有效 JSON。") from exc
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0].get("message"), dict):
        raise LLMCallError("模型服务响应缺少 choices[0].message。")
    return choices[0]["message"]
