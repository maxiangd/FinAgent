"""
系统日志配置
作用：配置统一的输出格式
loguru的好处：开箱即用，输出彩色日志

"""
import sys

from loguru import logger
from setuptools.command.setopt import edit_config

#移除默认的日志输出
logger.remove()

# 重配控制台sys输出格式
# format 日志格式=>时间|级别|文件名：行号|日志内容
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> |<level>{level}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan>-<level>{message}</level>",
)

# 同时把日志写入文件（每天一个文件，最多保留7天）
logger.add(
    "logs/app_{time:YYYY-MM-DD}.log",
    level="INFO",
    rotation="00:00", #每天0点创建文件夹
    retention="7 days", #最多保留7天的日志
    encoding="utf-8", # 使用utf-8 编码，避免中文乱码问题
)
