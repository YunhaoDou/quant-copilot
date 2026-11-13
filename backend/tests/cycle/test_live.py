"""真实源解析与异常语义的离线测试，不依赖外网。"""
import httpx
import pytest

from app.cycle import live, market
from app.cycle.engine import load_config


def test_pool_requires_matching_date_and_complete_rows():
    assert live.parse_pool({"data":{"qdate":20261106,"tc":0,"pool":[]}}, "20261106") == []
    with pytest.raises(ValueError):
        live.parse_pool({"data":{"qdate":20261105,"tc":0,"pool":[]}}, "20261106")
    with pytest.raises(ValueError):
        live.parse_pool({"data":{"qdate":20261106,"tc":2,"pool":[]}}, "20261106")
    with pytest.raises(ValueError):
        live.parse_pool({"data":None}, "20261106")


def test_leader_sort_and_missing_seal_data():
    rows = [{"c":"600001","n":"甲","lbc":2,"fbt":94500,"amount":100,"fund":20}, {"c":"000001","n":"乙","lbc":3,"fbt":100000,"amount":0}]
    result = live.leader_rows(rows)
    assert result[0]["symbol"] == "000001"
    assert result[0]["seal_ratio"] is None
    assert result[1]["first_limit_time"] == "09:45"


def test_minute_date_mismatch_is_not_reused():
    with pytest.raises(ValueError):
        live.parse_tencent_minutes({"data":{"sh000001":{"data":{"date":"20261105","data":["0930 3000 100"]}}}}, "sh000001", "上证", "20261106")


def test_sqlite_history_respects_observation_time(tmp_path):
    path = tmp_path / "snapshots.sqlite"
    live.store_snapshot({"date":"2026-11-06","state":"启动"}, "2026-11-06T10:00:00+08:00", path)
    live.store_snapshot({"date":"2026-11-06","state":"退潮"}, "2026-11-06T11:00:00+08:00", path)
    rows = live.read_history(10, "2026-11-06T10:30:00+08:00", path)
    assert len(rows) == 1 and rows[0]["state"] == "启动"


@pytest.mark.parametrize("symbol,expected", [("600519.SS","sh600519"),("000858","sz000858"),("510300","sh510300"),("920007","bj920007"),("sh000001","sh000001")])
def test_symbol_normalization(symbol, expected):
    assert market.normalize_symbol(symbol) == expected


def test_invalid_symbols_rejected():
    with pytest.raises(ValueError):
        market.normalize_symbol("https://example.com")


def test_partial_failure_keeps_missing_distinct_from_zero(monkeypatch):
    fields = ["0"]*50
    fields[1], fields[3], fields[30], fields[32], fields[33], fields[34], fields[37] = "上证指数", "3000", "20261106100000", "-1", "3100", "2900", "10000"
    quote = 'v_sh000001="' + "~".join(fields) + '";'
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=quote) if "qt.gtimg.cn" in str(request.url) else httpx.Response(503, text="上游不可用"))
    monkeypatch.setattr(live, "store_snapshot", lambda *a, **kw: None)
    monkeypatch.setattr(live, "read_history", lambda *a: [])
    monkeypatch.setattr(live, "captured_dates", lambda: [])
    result = live.LiveDataProvider(load_config(), transport=transport).fetch()
    assert result["simulated"] is False
    assert result["current"]["limit_up"] is None
    assert result["current"]["limit_down"] is None
    assert result["current"]["state"] == "数据不足"
    assert result["metadata"]["warnings"]


def _quote_text(**overrides):
    fields = ["0"]*50
    fields[1], fields[2], fields[3], fields[30], fields[32], fields[33], fields[34], fields[37] = (
        "上证指数", "000001", "3000", "20261106100000", "-1", "3100", "2900", "10000",
    )
    for index, value in overrides.items():
        fields[int(index.lstrip("f"))] = value
    return 'v_sh000001="' + "~".join(fields) + '";'


def test_index_parse_delegates_to_market_and_keeps_wan_yuan_amount():
    # 单一实现：market.parse_quotes 产出的 amount_yuan(元) 在这里换回看板沿用的万元口径。
    rows = market.parse_quotes(_quote_text())
    quotes = live.parse_quotes(_quote_text())
    assert rows[0]["amount_yuan"] == 10000 * 10000
    assert quotes[0]["amount"] == 10000
    assert quotes[0]["timestamp"] == rows[0]["quote_time"]
    assert quotes[0]["price"] == 3000 and quotes[0]["pct"] == -1


def test_index_parse_rejects_short_or_incomplete_payload():
    # 旧 >=38 宽松档不再接受；不完整行情必须硬失败而不是当完整快照。
    short = 'v_sh000001="' + "~".join(["0"]*40) + '";'
    with pytest.raises(ValueError, match="字段缺失"):
        live.parse_quotes(short)
    with pytest.raises(ValueError, match="字段缺失"):
        live.parse_quotes(_quote_text(f32=""))  # 缺涨跌幅


def test_replay_uses_only_saved_data_and_retains_minutes(tmp_path):
    path = tmp_path / "replay.sqlite"
    snapshot = {"date":"2026-11-06", "state":"启动"}
    live.store_snapshot(snapshot, "2026-11-06T10:00:00+08:00", path, details={"intraday":[{"time":"09:59","price":10}], "metadata":{"quote_time":"2026-11-06T09:59:00+08:00"}})
    live.store_snapshot({**snapshot,"state":"退潮"}, "2026-11-06T11:00:00+08:00", path)
    result = live.replay_dashboard(load_config(), "2026-11-06T10:30:00+08:00", path)
    assert result["current"]["state"] == "启动"
    assert result["intraday"][0]["price"] == 10
    assert result["metadata"]["replay"] is True
    assert result["metadata"]["refresh_seconds"] == 0
    assert live.replay_dashboard(load_config(), "2020-01-01", path)["current"] is None
