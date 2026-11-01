"""按 Agent 分配模型：解析优先级、角色校验与目录接口。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import agents.llm_provider_client as llm
from app.routers import providers
from app.schemas.analysis_schemas import AnalysisTaskRequest


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch):
    monkeypatch.setattr(
        llm, "load_llm_settings", lambda provider=None: SimpleNamespace(provider=provider)
    )


def test_agent_override_wins(monkeypatch):
    monkeypatch.setattr(llm, "agent_env_provider", lambda agent: "zhipu")
    state = {"provider": "qwen", "agent_providers": {"trader": "deepseek"}}

    assert llm.load_agent_settings(state, "trader").provider == "deepseek"


def test_env_default_used_without_override(monkeypatch):
    monkeypatch.setattr(llm, "agent_env_provider", lambda agent: "zhipu")
    state = {"provider": "qwen", "agent_providers": None}

    assert llm.load_agent_settings(state, "trader").provider == "zhipu"


def test_task_provider_is_last_fallback(monkeypatch):
    monkeypatch.setattr(llm, "agent_env_provider", lambda agent: None)
    state = {"provider": "qwen", "agent_providers": {"trader": ""}}

    assert llm.load_agent_settings(state, "trader").provider == "qwen"


def test_unknown_agent_key_rejected():
    with pytest.raises(ValidationError, match="未知的 Agent 角色"):
        AnalysisTaskRequest(stock_code="600519", agent_providers={"nobody": "zhipu"})


def test_known_agent_key_accepted():
    request = AnalysisTaskRequest(
        stock_code="600519", agent_providers={"portfolio_manager": "deepseek"}
    )

    assert request.agent_providers == {"portfolio_manager": "deepseek"}


def test_agent_catalog_covers_pipeline_roles():
    catalog = llm.agent_catalog()

    assert {item["key"] for item in catalog} == set(llm.AGENT_KEYS)
    assert all(item["label"] and item["stage_label"] for item in catalog)


def test_agent_catalog_endpoint():
    app = FastAPI()
    app.include_router(providers.router)

    response = TestClient(app).get("/api/providers/agents")

    assert response.status_code == 200
    assert response.json()[0]["key"] == "market_analyst"
