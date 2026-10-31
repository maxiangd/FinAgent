"""集中加载项目根目录的 .env，并提供带范围的整数读取。"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("finagent.config")

# backend/config/settings.py -> 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def get_env_str(name: str, default: str = "") -> str:
    """读取字符串配置，统一去掉首尾空白。"""
    return os.getenv(name, default).strip()


def get_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """读取整数配置并夹在 [minimum, maximum]；非法值回退默认值。"""
    raw = get_env_str(name) or str(default)
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s 必须是整数，已使用默认值 %s", name, default)
        value = default
    return min(max(value, minimum), maximum)
