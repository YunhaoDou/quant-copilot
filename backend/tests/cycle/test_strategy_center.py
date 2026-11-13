"""研究策略的证据门槛、退出与账户隔离。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cycle import events, strategy_center
from app.cycle.engine import load_config


def sample():
    return {
        "code": "600001", "cashPerShare": 5, "historicalCashPerShare": 4.5, "consecutiveYears": 7,
        "quality": {"status": "supported", "financialIndustry": False,
                    "payoutPct": 50, "fcfCover": 2, "ocfCover": 2.2,
                    "cashProfitRatio": 1.1, "deductedProfits": [130, 100, 90]},
    }


def test_independent_strategy_criteria_and_unknown_are_explainable():
    config = load_config()
    quote = {"price": 100, "pe": 10, "pb": 1}
    metrics = {"ma20": 95, "ma60": 90, "high20": 99, "return_base": 80, "benchmark_return": 5, "volatility": 20}
    for spec in strategy_center.RESEARCH_CATALOG:
        result = strategy_center.evaluate(spec["id"], sample(), quote, metrics, {"yieldPct": 1.5}, config)
        assert result["status"] == "pass", spec["id"]
    assert strategy_center.evaluate("dividend-cash", sample(), quote, metrics, None, config)["status"] == "unknown"
    bad = strategy_center.evaluate("quality-value", sample(), {**quote, "pe": 30}, metrics, None, config)
    assert bad["status"] == "fail" and bad["exit_failed"]
    # 突破条件不再满足，但趋势及相对强势仍在时不因此强制退出。
    hold = strategy_center.evaluate("relative-trend", sample(), quote, {**metrics, "high20": 110}, None, config)
    assert hold["status"] == "fail" and not hold["exit_failed"]


def test_account_start_and_pause_are_isolated_and_legacy_is_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "strategies.sqlite")
    monkeypatch.setattr(strategy_center, "enqueue_refresh", lambda: None)
    from app.cycle import shibor_sim
    monkeypatch.setattr(shibor_sim._executor,"submit",lambda *args:None)
    app = FastAPI()
    app.include_router(strategy_center.router)
    client = TestClient(app)
    result = client.post("/strategy-center/start-all")
    assert result.status_code == 200
    strategies = result.json()["strategies"]
    assert len(strategies) == 8
    assert all(s["account"]["cash"] == 100000 for s in strategies if s["id"] != "leader-rebound")
    # 情绪龙头回补沿用旧影子账户：目录页必须能显示它的运行状态与参考权益（不再写死 None）。
    leader = next(s for s in strategies if s["id"] == "leader-rebound")
    assert leader["account"] is not None
    assert leader["account"]["status"] == "running"
    assert leader["account"]["equity"] == 100000
    assert client.post("/strategy-center/quality-value/pause").status_code == 200
    fresh = client.get("/strategy-center").json()["strategies"]
    assert fresh[0]["account"]["status"] == "paused"
    assert fresh[1]["account"]["status"] == "running"
    with events.database() as db:
        assert db.execute("SELECT COUNT(*) FROM strategy_sim").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM research_strategy_accounts").fetchone()[0] == 5
    assert client.post("/strategy-center/unknown/start").status_code == 404


def test_complete_candidates_are_queryable_beyond_preview(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "candidates.sqlite")
    with events.database() as db:
        strategy_center.schema(db)
        db.executemany("INSERT INTO research_candidate_checks VALUES(?,?,?,?,?)", [
            ("quality-value",str(600000+i),"unknown" if i==250 else "fail",i,json.dumps({"code":str(600000+i),"name":f"样本{i}","status":"unknown" if i==250 else "fail"})) for i in range(321)
        ])
    app=FastAPI();app.include_router(strategy_center.router);client=TestClient(app)
    root="/strategy-center/quality-value/candidates"
    first=client.get(root).json()
    assert first["total"]==321 and len(first["rows"])==50
    assert client.get(root+"?page=7").json()["rows"][-1]["code"]=="600320"
    assert client.get(root+"?query=600250").json()["rows"][0]["name"]=="样本250"
    assert client.get(root+"?status=unknown").json()["total"]==1
    assert client.get(root+"?status=invalid").status_code==422
