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
            url = get_env_str("MONGO_URL", "mongodb://127.0.0.1:27017")
            db_name = get_env_str("MONGO_DB", "finagent")
            try:
                from pymongo import ASCENDING, MongoClient

                client = MongoClient(url, serverSelectionTimeoutMS=1500)
                client.admin.command("ping")
                collection = client[db_name][_COLLECTION]
                collection.create_index([("task_id", ASCENDING)], unique=True)
                collection.create_index([("created_at", ASCENDING)])
                self._collection = collection
                logger.info("任务持久化：MongoDB（%s/%s）", _mask_url(url), db_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MongoDB 不可用（%s），任务只保存在进程内", type(exc).__name__
                )
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


task_repository = TaskRepository()
