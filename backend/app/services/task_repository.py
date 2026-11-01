"""任务与报告的 MongoDB 持久化；Mongo 不可用时静默降级为仅内存。"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from config.settings import get_env_str

logger = logging.getLogger("finagent.task_repository")

_COLLECTION = "analysis_tasks"


def _mask_url(url: str) -> str:
    """日志里隐藏连接串中的密码。"""
    return re.sub(r"//[^@/]+@", "//***@", url)


_mongo_client = None
_mongo_checked = False
_mongo_lock = threading.Lock()


def get_mongo_client():
    """返回已连接的 MongoClient；不可用时返回 None（只尝试一次）。"""
    global _mongo_client, _mongo_checked
    if _mongo_checked:
        return _mongo_client
    with _mongo_lock:
        if _mongo_checked:
            return _mongo_client
        _mongo_checked = True
        url = get_env_str("MONGO_URL", "mongodb://127.0.0.1:27017")
        try:
            from pymongo import MongoClient

            client = MongoClient(url, serverSelectionTimeoutMS=1500)
            client.admin.command("ping")
            _mongo_client = client
            logger.info("MongoDB 已连接（%s）", _mask_url(url))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "MongoDB 不可用（%s），任务与模拟交易只保存在进程内", type(exc).__name__
            )
            _mongo_client = None
        return _mongo_client


def get_mongo_db_name() -> str:
    return get_env_str("MONGO_DB", "finagent")


class TaskRepository:
    """把任务文档写入 MongoDB，供服务重启后查询。"""

    def __init__(self) -> None:
        self._collection = None
        self._checked = False
        self._lock = threading.Lock()

    def _ensure(self):
        """首次使用时连接并建索引；失败后不再重试，避免每个请求都等超时。"""
        if self._checked:
            return self._collection
        with self._lock:
            if self._checked:
                return self._collection
            self._checked = True
            client = get_mongo_client()
            if client is None:
                self._collection = None
                return None
            try:
                from pymongo import ASCENDING

                collection = client[get_mongo_db_name()][_COLLECTION]
                collection.create_index([("task_id", ASCENDING)], unique=True)
                collection.create_index([("created_at", ASCENDING)])
                self._collection = collection
            except Exception as exc:  # noqa: BLE001
                logger.warning("任务集合初始化失败：%s", exc)
                self._collection = None
            return self._collection

    def save(self, document: dict[str, Any]) -> None:
        """按 task_id upsert 整份任务文档。"""
        collection = self._ensure()
        if collection is None:
            return
        try:
            collection.update_one(
                {"task_id": document["task_id"]},
                {"$set": document},
                upsert=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("任务写入 MongoDB 失败：%s: %s", type(exc).__name__, exc)

    def get(self, task_id: str) -> dict[str, Any] | None:
        collection = self._ensure()
        if collection is None:
            return None
        try:
            return collection.find_one({"task_id": task_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("任务读取失败：%s: %s", type(exc).__name__, exc)
            return None

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        collection = self._ensure()
        if collection is None:
            return []
        try:
            cursor = (
                collection.find({"task_id": {"$exists": True}})
                .sort("created_at", -1)
                .limit(max(1, min(limit, 100)))
            )
            return list(cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("任务列表读取失败：%s: %s", type(exc).__name__, exc)
            return []

    def delete(self, task_id: str) -> None:
        collection = self._ensure()
        if collection is None:
            return
        try:
            collection.delete_one({"task_id": task_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("任务删除失败：%s: %s", type(exc).__name__, exc)


task_repository = TaskRepository()
