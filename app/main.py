from fastapi import FastAPI

from app.core.logger import logger
from app.core.config import settings
from app.schemas.common import ajax_success,ajax_error

app=FastAPI(title="Supply Guard")

@app.get("/")
def home():
    logger.info("Home page visited")
    return {"message"}

@app.get("/test/success")
def test_success():
    """测试成功接口"""
    return ajax_success({"message": "测试成功"})

@app.get("/test/error")
def test_error():
    """测试错误接口"""

    return ajax_error({"message": "测试失败"})
