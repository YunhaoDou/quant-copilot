"""事件首次证据不变、跨日接续、缺失语义及执行记录幂等测试。"""
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cycle import events


def capture(day="2026-11-11", clock="10:00:00", started=True, count=3):
    quote = f"{day}T{clock}+08:00"
    sector = {"code": "BK0448", "name": "通信设备", "pct": 4.5 if started else 2,
              "limit_up": count, "started": started,
              "checks": {"涨幅": started, "涨停": True, "时间": True}}
    snapshot = {"date": day, "market_pct": .5, "risk": "关注", "new_low": None, "broken_leaders": [],
                "rule_version": "test", "limit_down": 0}
    metadata = {"quote_time": quote, "fetched_at": quote, "feeds": {"涨停池": {"status": "正常"}, "炸板池": {"status": "正常"}}}
    leaders = [{"symbol": f"{i:06d}", "name": f"候选{i}", "sector": "通信设备", "boards": 2} for i in range(1, 16)]
    return snapshot, metadata, [sector], leaders


def test_first_snapshot_is_immutable_and_all_matching_candidates_survive(tmp_path):
    path = tmp_path / "events.sqlite"
    events.ingest(*capture(), path=path)
    first = events.list_events(path)[0]
    events.ingest(*capture(clock="10:01:00", count=5), path=path)
    events.ingest(*capture(clock="09:59:00"), path=path)
    current = events.detail(first["id"], path)
    assert len(events.list_events(path)) == 1
    assert len(current["history"]) == 2
    assert len(current["latest"]["leaders"]) == 15
    assert current["first"]["sector"]["limit_up"] == 3
    assert current["latest"]["sector"]["limit_up"] == 5
    assert current["evidence"]["limit_up_change"] == 2
    events.ingest(*capture(day="2026-11-12", started=False), path=path)
    current = events.detail(first["id"], path)
    assert current["dates"] == ["2026-11-11", "2026-11-12"]
    assert current["evidence"]["state"] == "启动条件已消失"
    events.ingest(*capture(day="2026-11-12", clock="10:01:00"), path=path)
    assert events.detail(first["id"], path)["evidence"]["state"] == "启动条件重新满足"


def test_stale_quotes_and_missing_pools_are_not_invented(tmp_path):
    path = tmp_path / "events.sqlite"
    args = capture()
    args[1]["fetched_at"] = "2026-11-11T10:04:00+08:00"
    events.ingest(*args, path=path)
    assert events.list_events(path) == []
    args = capture()
    args[1]["feeds"]["涨停池"]["status"] = "不可用"
    args[2][0]["checks"]["涨停"] = None
    # 无法确认三项条件时，不产生新的启动事件。
    args[2][0]["started"] = False
    events.ingest(*args, path=path)
    assert events.list_events(path) == []
    events.ingest(*capture(), path=path)
    events.ingest(*args, path=path)
    assert len(events.list_events(path)) == 1


def test_departed_candidates_keep_quotes_and_missing_pool_stays_unknown(tmp_path):
    path = tmp_path / "events.sqlite"
    events.ingest(*capture(), path=path)
    snapshot, metadata, sectors, leaders = capture(clock="10:01:00")
    metadata["feeds"]["涨停池"]["status"] = "不可用"
    sectors[0]["checks"]["涨停"] = None
    sectors[0]["started"] = False
    snapshot["candidate_quotes"] = [{"code": "000001", "price": 12, "pct": -2, "quote_time": metadata["quote_time"]}]
    events.ingest(snapshot, metadata, sectors, [], path=path)
    event = events.list_events(path)[0]
    assert event["evidence"]["state"] == "数据不足"
    assert event["latest"]["leaders"] is None
    assert len(event["latest"]["watched"]) == 15
    assert event["latest"]["watched"][0]["quote"]["price"] == 12
    assert event["latest"]["watched"][1]["quote"] is None


def test_api_execution_records_retry_and_closed_event_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "events.sqlite")
    events.ingest(*capture())
    event_id = events.list_events()[0]["id"]
    app = FastAPI()
    app.include_router(events.router)
    client = TestClient(app)
    record = {"id": str(uuid.uuid4()), "kind": "实际成交", "action": "买入", "symbol": "002313",
              "text": "按券商成交回报登记", "price": 10, "quantity": 100}
    endpoint = f"/cycle/events/{event_id}/records"
    assert client.post(endpoint, json=record).status_code == 200
    assert client.post(endpoint, json=record).status_code == 200
    assert len(client.get(f"/cycle/events/{event_id}").json()["records"]) == 1
    assert client.post(endpoint, json={**record, "quantity": 200}).status_code == 409
    assert client.post(endpoint, json={**record, "id": str(uuid.uuid4()), "symbol": ""}).status_code == 422
    plan = {"stage": "分歧观察", "plan": "观察收盘证据", "invalidation": "启动条件消失后复核", "status": "closed"}
    assert client.patch(f"/cycle/events/{event_id}", json=plan).status_code == 200
    events.ingest(*capture(clock="10:02:00"))
    saved = events.detail(event_id)
    assert saved["status"] == "closed" and saved["plan"] == plan["plan"]
    assert len(saved["history"]) == 1
    events.ingest(*capture(day="2026-11-12"))
    assert len(events.list_events()) == 2
