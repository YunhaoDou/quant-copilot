"""分页不得缩小全集、混合版本或改变未知值；测试只使用临时库。"""
import copy,json,sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.cycle import dividends,events,read_api,read_cache

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    path=tmp_path/"dividends.sqlite";monkeypatch.setattr(dividends,"DB_PATH",path)
    rows=[dict(code=str(600000+i),name=f"样本{i}",category="金融" if i%2==0 else "工业",sector="银行" if i%2==0 else "材料",dividendYield=None if i==320 else i/100,signal="stage" if i%3==0 else "watch",quality={"status":"supported" if i%2==0 else "unknown"},screening={"status":["pass","fail","unknown","manual"][i%4]}) for i in range(321)]
    payload=dict(status="ready",progress="完成",updatedAt="2026-11-13T10:00:00+08:00",tradeDate="2026-11-13",strategyVersion=4,stocks=rows,failures=["异常"+str(i) for i in range(123)],checked=321,scanned=321,preselected=81,config={},notes=[])
    def put(value):
        with sqlite3.connect(path) as db:db.execute("CREATE TABLE IF NOT EXISTS board(id INTEGER PRIMARY KEY,payload TEXT)");db.execute("INSERT OR REPLACE INTO board VALUES(1,?)",(json.dumps(value,ensure_ascii=False),))
        read_cache.invalidate_documents()
    put(payload);monkeypatch.setattr(dividends,"_state",copy.deepcopy(payload));monkeypatch.setattr(dividends,"screen_candidate",lambda s,b,c:s["screening"])
    app=FastAPI();app.include_router(read_api.router);app.include_router(dividends.router)
    return TestClient(app),payload,put


def test_all_pages_equal_entire_original_without_320_cap(fixture):
    client,p,_=fixture;summary=client.get("/dividends/summary").json();version=summary["snapshot_version"]
    actual=[]
    for page in range(1,8):
        d=client.get("/dividends/stocks",params={"page":page,"version":version}).json();actual.extend(d["stocks"]);assert d["matched"]==321
    assert actual==p["stocks"] and actual[-1]["dividendYield"] is None
    assert client.get("/dividends").json()==dividends.board()


def test_filters_counts_selection_and_all_failures_are_preserved(fixture):
    client,_,_=fixture
    d=client.get("/dividends/stocks",params={"category":"金融","only_low":True,"screen":"pass"}).json()
    assert d["matched"]==27 and [r["code"] for r in d["stocks"]]==[str(600000+i) for i in range(0,321,12)]
    d=client.get("/dividends/stocks",params={"selected":"600320"}).json();assert d["selected_stock"]["code"]=="600320"
    assert client.get("/dividends/stocks",params={"query":"样本320"}).json()["stocks"][0]["dividendYield"] is None
    errors=[]
    for page in [1,2,3]:errors+=client.get("/dividends/failures",params={"page":page}).json()["rows"]
    assert len(errors)==123 and errors[-1]=="异常122"
    assert client.get("/dividends/stocks",params={"screen":"invalid"}).status_code==422


def test_pinned_version_survives_new_snapshot_and_invalid_version_rejected(fixture):
    client,p,put=fixture;v=client.get("/dividends/summary").json()["snapshot_version"]
    changed=copy.deepcopy(p);changed["stocks"][0]["name"]="新快照";put(changed)
    new=client.get("/dividends/summary").json()["snapshot_version"];assert new!=v
    assert client.get("/dividends/stocks",params={"version":v}).json()["stocks"][0]["name"]=="样本0"
    assert client.get("/dividends/stocks",params={"version":new}).json()["stocks"][0]["name"]=="新快照"
    assert client.get("/dividends/stocks",params={"version":"not-retained"}).status_code==409


def test_etag_progress_changes_but_page_does_not_retransfer(fixture,monkeypatch):
    client,p,_=fixture;r=client.get("/dividends/stocks");again=client.get("/dividends/stocks",headers={"If-None-Match":r.headers["etag"]})
    assert again.status_code==304 and not again.content
    before=client.get("/dividends/summary")
    dividends._state.update(status="running",progress="进行中",checked=7)
    after=client.get("/dividends/summary",headers={"If-None-Match":before.headers["etag"]})
    assert after.status_code==200 and after.json()["checked"]==7
    assert client.get("/dividends/stocks",headers={"If-None-Match":r.headers["etag"]}).status_code==304


def test_screening_pages_keep_unknown_rank_and_all_321_symbols(tmp_path,monkeypatch):
    monkeypatch.setattr(events,"DB_PATH",tmp_path/"events.sqlite")
    rows=[dict(symbol=str(600000+i),rank=i+1,composite_score=i,factors={},reasons=[]) for i in range(321)]
    rows[-1].update(rank=None,composite_score=None)
    with sqlite3.connect(events.DB_PATH) as db:
        db.execute("CREATE TABLE full_stock_screening(id INTEGER PRIMARY KEY,payload TEXT)");db.execute("INSERT INTO full_stock_screening VALUES(1,?)",(json.dumps(dict(results=rows,universe_size=321,scored=320,unknown=1,status="ready")),))
    app=FastAPI();app.include_router(read_api.router);client=TestClient(app)
    got=[]
    for page in range(1,8):got+=client.get("/screening/results",params={"page":page}).json()["results"]
    assert got==rows and got[-1]["rank"] is None
