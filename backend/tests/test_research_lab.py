"""迁移研究功能：风险数学、禁止净值错配、档案持久化、脱敏与可恢复迁移。"""
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import numpy as np
import pandas as pd
import pytest

from app.services import research_lab as lab, research_store as store, fund_analysis
from app.routes import research_lab as routes
from app.main import app


@pytest.fixture
def private_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "private.sqlite")
    monkeypatch.setattr(routes, "_cache", {})
    return tmp_path


def bars(n=40):
    return pd.DataFrame([dict(trade_date=str(date(2026, 1, 1) + timedelta(days=i)), open=100+i, high=102+i, low=99+i, close=101+i, volume=1000+i) for i in range(n)])


def test_risk_tail_and_null_denominators():
    m = lab.metrics([100, 50, 75, 75])
    assert m["max_drawdown"] == -50
    assert m["cvar95"] >= m["var95"] > 0
    flat = lab.metrics([100]*30)
    assert flat["sharpe"] is None and flat["profit_loss_ratio"] is None
    assert flat["var95"] == 0


@pytest.mark.parametrize("values", [[], [1], [0, 1], [1, -1]])
def test_invalid_metrics_fail(values):
    with pytest.raises(ValueError):
        lab.metrics(values)


def test_technical_warmup_and_flat_rsi():
    df = bars(220)
    df["close"] = 100.
    result = lab.technical_frame(df)
    assert result.rsi.iloc[-1] == 50
    assert np.isnan(result.ma200.iloc[198])
    assert result.ma200.iloc[199] == 100
    assert result.histogram.iloc[-1] == 0


def test_simulation_seed_contributions_and_no_false_forecast():
    args = dict(capital=100000, monthly=5000, years=5, annual_return=.06, volatility=.2, target=500000)
    a, b = lab.monte_carlo(**args), lab.monte_carlo(**args)
    assert {k:v for k,v in a.items() if k != "fetched_at"} == {k:v for k,v in b.items() if k != "fetched_at"}
    assert a["path"][-1]["contributed"] == 400000
    assert 0 <= a["target_probability"] <= 100
    assert all(r["p5"] <= r["median"] <= r["p95"] for r in a["path"])
    zero = lab.monte_carlo(100, 10, 1, 0, 0, 220, 100)
    assert zero["path"][-1]["median"] == 220
    assert "假设" in a["source"]


def test_diagnosis_news_failure_stays_explicit(monkeypatch):
    monkeypatch.setattr(lab, "fetch_daily", lambda *a: bars())
    monkeypatch.setattr(lab, "fetch_quotes", lambda *a: {"quotes": [{"name": "测试证券"}]})
    monkeypatch.setattr(lab, "_fetch_headlines", lambda *a: (_ for _ in ()).throw(ValueError("unavailable")))
    result = lab.diagnose("600519", 40, 100000, 1, 10)
    assert not result["news"]["items"]
    assert "暂不可用" in result["news"]["status"]
    assert result["sizing"]["position_cap"] <= 10000
    assert result["currency"] == "CNY"


def test_fund_nav_never_shifted_or_forward_filled(monkeypatch):
    df = bars(3).rename(columns={"trade_date": "date"})
    monkeypatch.setattr(lab, "fetch_daily", lambda *a, **kw: df.rename(columns={"date": "trade_date"}))
    monkeypatch.setattr(lab, "nav_history", lambda *a: pd.DataFrame([dict(date=df.date.iloc[0], nav=100, acc_nav=100), dict(date=df.date.iloc[2], nav=100, acc_nav=100)]))
    monkeypatch.setattr(fund_analysis, "get_premium_snapshot", lambda *a: None)
    result = lab.fund_deep("510300", 30)
    assert [r["date"] for r in result["premium_history"]] == [df.date.iloc[0], df.date.iloc[2]]
    assert result["chart"][1]["nav"] is None


def test_threshold_order_rejected():
    with pytest.raises(ValueError, match="阈值"):
        lab.fund_deep("510300", warning_high=5, danger_high=3)


def test_nav_pagination_uses_all_pages_and_detects_duplicates(monkeypatch):
    client = httpx.Client
    calls = []
    def response(req):
        page = int(req.url.params["pageIndex"])
        calls.append(page)
        assert req.url.params["pageSize"] == "20"
        rows = [dict(FSRQ=str(date(2026, 11, 6)-timedelta(days=i)), DWJZ="1.1", LJJZ="1.2") for i in range((page-1)*20, min(page*20, 41))]
        return httpx.Response(200, json={"TotalCount": 41, "Data": {"LSJZList": rows}})
    monkeypatch.setattr(lab.httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(response)))
    assert len(lab.nav_history("510300", 41)) == 41
    assert sorted(calls) == [1, 2, 3]


def test_secret_config_never_round_trips(private_store):
    secret = "test-key-never-returned"
    result = store.save_config({"providers": {"openai": {"api_key": secret}}, "notifications": {"lark": "https://example.com/private-webhook"}, "proxy": "http://user:pass@127.0.0.1:9999"})
    encoded = json.dumps(result)
    assert secret not in encoded and "private-webhook" not in encoded and "user:pass" not in encoded
    assert result["providers"]["openai"]["key_set"] is True
    assert store.DB_PATH.stat().st_mode & 0o777 == 0o600
    store.save_config({"providers": {"openai": {"api_key": ""}}})
    assert store.config()["providers"]["openai"]["api_key"] == secret


@pytest.mark.parametrize("pid", ["deepseek", "openai", "gemini", "anthropic"])
def test_provider_adapters(private_store, monkeypatch, pid):
    cfg = store.config()
    cfg["active_provider"] = pid
    cfg["providers"][pid].update(api_key="synthetic-key", model="test-model")
    client = httpx.Client
    def respond(req):
        body = json.loads(req.content)
        assert body["model"] == "test-model"
        if pid == "anthropic":
            assert req.url.path.endswith("/messages")
            return httpx.Response(200, json={"content": [{"type": "text", "text": "连接成功"}]})
        assert req.url.path.endswith("/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": "连接成功"}}]})
    monkeypatch.setattr(store.httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(respond)))
    assert store.complete([{"role": "user", "content": "连接测试"}], cfg)["content"] == "连接成功"


def test_reports_chats_filters_clear_and_import_idempotence(private_store, monkeypatch):
    payload = {"kind": "fund", "code": "510300", "name": "测试档案", "source": "测试数据"}
    rid = store.save_report(payload, "stable-id")
    assert store.save_report(payload, "stable-id") == rid
    assert len(store.reports("5103")) == 1
    monkeypatch.setattr(store, "complete", lambda *a, **kw: {"content": "标注假设的模型观点"})
    store.ask(rid, "风险是什么？")
    assert [r["role"] for r in store.chats(rid)] == ["user", "assistant"]
    store.clear(rid, chat_only=True)
    assert not store.chats(rid) and store.report(rid)
    store.clear(rid)
    assert not store.reports()


def test_migration_backup_verified_and_source_preserved(private_store, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "tools/migrate_legacy_terminal.py"
    spec = importlib.util.spec_from_file_location("migration_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = private_store / "legacy"
    (source / "fund").mkdir(parents=True)
    (source / "fund/config.json").write_text(json.dumps({"providers": {}, "search_history": []}))
    (source / "app.py").write_text("# 保留用户源文件")
    result = module.migrate(source, private_store / "backup")
    assert result["verified_files"] == 2
    assert (source / "app.py").exists()
    assert Path(result["archive"]).exists()
    assert result["source_removed"] is False


def test_lab_routes_archive_and_validation(private_store):
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/research-lab/config").status_code == 200
        assert client.post("/research-lab/simulate", json={"years": 0}).status_code == 422
        r = client.post("/research-lab/simulate", json={"years": 1, "simulations": 100})
        assert r.status_code == 200
        rid = r.json()["id"]
        assert client.get(f"/research-lab/reports/{rid}").json()["kind"] == "simulation"
        assert client.get(f"/research-lab/reports/{rid}/notification-preview").status_code == 200
        assert client.delete(f"/research-lab/reports/{rid}").status_code == 200
        assert client.get("/research-lab/reports").json() == []
