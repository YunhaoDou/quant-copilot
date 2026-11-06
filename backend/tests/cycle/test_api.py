"""验证无需数据库的实际路由和异常响应。"""
from fastapi.testclient import TestClient

from app.cycle.api import app

client = TestClient(app)


def test_offline_dashboard_and_backtest():
    response = client.get("/cycle?source=mock")
    assert response.status_code == 200
    data = response.json()
    assert data["simulated"] is True
    assert len(data["history"]) == 120
    assert data["backtest"]["summary"]["samples"] > 0


def test_provider_errors_and_bad_horizon():
    assert client.get("/cycle?source=akshare&as_of=2026-01-01").status_code == 422
    assert client.get("/cycle?horizon=99").status_code == 422


def test_api_replay_never_includes_future():
    data = client.get("/cycle?source=mock&as_of=2026-02-10").json()
    assert all(day["date"] <= "2026-02-10" for day in data["history"])
    assert all(day["date"] <= "2026-02-10" for day in data["backtest"]["simulation"]["curve"])
