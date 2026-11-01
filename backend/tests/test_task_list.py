"""任务列表：重启前未结束的任务显示为中断失败，并允许删除。"""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.task_manager as task_manager_module
from app.routers import agent_tasks
from app.schemas.analysis_schemas import AnalysisTaskRequest, TaskStatus
from app.services.task_manager import TaskManager, TaskRecord


def _doc(task_id: str, status: str) -> dict:
    return {"task_id": task_id, "status": status}


def test_stale_running_document_is_shown_as_interrupted(monkeypatch):
    monkeypatch.setattr(
        task_manager_module.task_repository,
        "list_recent",
        lambda limit: [_doc("stale", "running")],
    )

    result = TaskManager().list_tasks(10)

    assert result[0]["status"] == "failed"
    assert result[0]["error"]["code"] == "interrupted"


def test_running_task_of_current_process_is_kept(monkeypatch):
    manager = TaskManager()
    manager._tasks["live"] = TaskRecord(
        task_id="live",
        request=AnalysisTaskRequest(stock_code="600519"),
        status=TaskStatus.RUNNING,
    )
    monkeypatch.setattr(
        task_manager_module.task_repository,
        "list_recent",
        lambda limit: [_doc("live", "running")],
    )

    result = manager.list_tasks(10)

    assert result[0]["status"] == "running"


def test_finished_document_is_untouched(monkeypatch):
    document = _doc("done", "completed")
    monkeypatch.setattr(
        task_manager_module.task_repository,
        "list_recent",
        lambda limit: [document],
    )

    result = TaskManager().list_tasks(10)

    assert result[0] is document
    assert "error" not in result[0]


def test_stale_running_task_becomes_failed_and_deletable(monkeypatch):
    document = {
        "task_id": "stale",
        "status": "running",
        "request": {"stock_code": "600519"},
    }
    deleted: list[str] = []
    monkeypatch.setattr(
        task_manager_module.task_repository, "get", lambda task_id: document
    )
    monkeypatch.setattr(task_manager_module.task_repository, "save", lambda doc: None)
    monkeypatch.setattr(
        task_manager_module.task_repository, "delete", deleted.append
    )

    manager = TaskManager()
    record = manager.get_task("stale")

    assert record.status is TaskStatus.FAILED
    assert record.error.code == "interrupted"

    manager.delete_task("stale")
    assert deleted == ["stale"]
    assert "stale" not in manager._tasks


def test_list_endpoint_exposes_report_summary(monkeypatch):
    now = datetime.now(timezone.utc)
    documents = [
        {
            "task_id": "done",
            "status": "completed",
            "request": {"stock_code": "600519", "period": "daily"},
            "created_at": now,
            "updated_at": now,
            "result": {"stock_name": "贵州茅台", "pm_decision": {"action": "buy"}},
        },
        {
            "task_id": "broken",
            "status": "failed",
            "request": {"stock_code": "000001", "period": "daily"},
            "created_at": now,
            "updated_at": now,
        },
    ]
    monkeypatch.setattr(
        agent_tasks.task_manager, "list_tasks", lambda limit: documents
    )
    app = FastAPI()
    app.include_router(agent_tasks.router)

    response = TestClient(app).get("/api/agent/tasks?limit=10")

    assert response.status_code == 200
    completed, failed = response.json()
    assert completed["stock_name"] == "贵州茅台"
    assert completed["pm_action"] == "buy"
    assert failed["stock_name"] is None
    assert failed["pm_action"] is None
