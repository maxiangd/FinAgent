"""删除任务与报告：路由状态校验、内存与 Mongo 一并清理。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.task_manager as task_manager_module
from app.routers import agent_tasks
from app.schemas.analysis_schemas import AnalysisTaskRequest, TaskStatus
from app.services.task_manager import TaskRecord, TaskManager


@pytest.fixture
def api(monkeypatch):
    record = TaskRecord(
        task_id="task-1",
        request=AnalysisTaskRequest(stock_code="600519"),
        status=TaskStatus.COMPLETED,
    )
    deleted: list[str] = []
    monkeypatch.setattr(
        agent_tasks.task_manager,
        "get_task",
        lambda task_id: record if task_id == record.task_id else None,
    )
    monkeypatch.setattr(agent_tasks.task_manager, "delete_task", deleted.append)

    app = FastAPI()
    app.include_router(agent_tasks.router)
    return SimpleNamespace(client=TestClient(app), record=record, deleted=deleted)


def test_delete_completed_task(api):
    response = api.client.delete("/api/agent/tasks/task-1")

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-1", "deleted": True}
    assert api.deleted == ["task-1"]


def test_delete_running_task_is_rejected(api):
    api.record.status = TaskStatus.RUNNING

    response = api.client.delete("/api/agent/tasks/task-1")

    assert response.status_code == 409
    assert api.deleted == []


def test_delete_unknown_task_returns_404(api):
    response = api.client.delete("/api/agent/tasks/missing")

    assert response.status_code == 404
    assert api.deleted == []


def test_manager_delete_clears_memory_and_repository(monkeypatch):
    persisted: list[str] = []
    monkeypatch.setattr(
        task_manager_module.task_repository, "delete", persisted.append
    )
    manager = TaskManager()
    manager._tasks["task-1"] = TaskRecord(
        task_id="task-1",
        request=AnalysisTaskRequest(stock_code="600519"),
        status=TaskStatus.COMPLETED,
    )

    manager.delete_task("task-1")

    assert "task-1" not in manager._tasks
    assert persisted == ["task-1"]


@pytest.fixture
def batch_api(monkeypatch):
    records = {
        task_id: TaskRecord(
            task_id=task_id,
            request=AnalysisTaskRequest(stock_code="600519"),
            status=status,
        )
        for task_id, status in (
            ("done-1", TaskStatus.COMPLETED),
            ("done-2", TaskStatus.FAILED),
            ("running", TaskStatus.RUNNING),
        )
    }
    deleted: list[str] = []
    monkeypatch.setattr(
        agent_tasks.task_manager, "get_task", lambda task_id: records.get(task_id)
    )
    monkeypatch.setattr(agent_tasks.task_manager, "delete_task", deleted.append)

    app = FastAPI()
    app.include_router(agent_tasks.router)
    return SimpleNamespace(client=TestClient(app), deleted=deleted)


def test_batch_delete_skips_running_and_missing(batch_api):
    response = batch_api.client.post(
        "/api/agent/tasks/batch-delete",
        json={"task_ids": ["done-1", "done-2", "running", "missing", "done-1"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "deleted": ["done-1", "done-2"],
        "skipped": ["running", "missing"],
    }
    assert batch_api.deleted == ["done-1", "done-2"]


def test_batch_delete_rejects_empty_list(batch_api):
    response = batch_api.client.post(
        "/api/agent/tasks/batch-delete", json={"task_ids": []}
    )

    assert response.status_code == 422
    assert batch_api.deleted == []
