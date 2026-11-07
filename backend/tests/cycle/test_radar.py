"""事实雷达：样本范围、完整日线、缺失值和板块日期不得混淆。"""
from datetime import datetime

import pandas as pd
import pytest

from app.cycle import radar
from app.cycle.engine import load_config
from app.cycle.live import TZ


def test_turnover_ratio_excludes_current_day_from_baseline():
    frame = pd.DataFrame({"trade_date": pd.date_range("2026-01-01", periods=21).strftime("%Y-%m-%d"), "close": list(range(100, 121)), "volume": [100]*20+[200]})
    r = radar.trend_facts(frame)
    assert r["volume_ratio"] == 2
    assert r["ma60"] is None and r["ma200"] is None
    assert "不代表全市场" in r["scope"]


def test_insufficient_daily_data_is_not_filled():
    with pytest.raises(ValueError):
        radar.trend_facts(pd.DataFrame({"close": [1]}))


def sector(code, change, day="2026-11-06"):
    return dict(f12=code, f14=code, f3=change, f124=datetime.fromisoformat(day+"T15:00:00+08:00").timestamp())


def test_sector_breadth_counts_industries_and_drops_wrong_day():
    rows = [sector("a", 2), sector("b", -1), sector("c", 0), sector("d", 99, "2026-11-05"), sector("e", None)]
    r = radar.sector_facts(rows, "2026-11-06")
    assert (r["advancing"], r["declining"], r["flat"]) == (1, 1, 1)
    assert r["covered"] == 3 and r["omitted"] == 2
    assert r["rows"][0]["code"] == "a"
    assert "非上涨/下跌股票家数" in r["scope"]


def test_sector_reference_without_quote_never_mixes_dates():
    r = radar.sector_facts([sector("old", 10, "2026-11-05"), sector("new", -1)])
    assert r["data_date"] == "2026-11-06"
    assert [row["code"] for row in r["rows"]] == ["new"]


def test_partial_sources_preserve_unknown_and_pool_formula(monkeypatch):
    closed = []
    class Provider:
        def __init__(self, cfg):
            self.client = self
        def close(self):
            closed.append(True)
        def sectors(self):
            return [sector("x", 1)]
        def pool(self, endpoint, day):
            assert day == "20261106"
            if endpoint == "getTopicDTPool":
                raise ValueError("源不可用")
            return [{}, {}] if endpoint == "getTopicZTPool" else [{}]
    monkeypatch.setattr(radar, "LiveDataProvider", Provider)
    monkeypatch.setattr(radar, "fetch_quotes", lambda *a: {"quotes": [{"quote_time": "2026-11-06T15:00:00+08:00"}]})
    monkeypatch.setattr(radar, "fetch_daily", lambda *a: (_ for _ in ()).throw(ValueError("无日线")))
    result = radar.fetch_radar(load_config())
    assert result["trend"] is None
    assert result["sentiment"]["limit_down"] is None
    assert result["sentiment"]["break_rate"] == pytest.approx(100/3)
    assert result["feeds"]["limit_down"]["status"] == "不可用"
    assert "score" not in result and "position" not in result
    assert closed


def test_missing_quote_never_uses_todays_date_for_old_pools(monkeypatch):
    class Provider:
        def __init__(self, cfg):
            self.client = self
        def close(self):
            pass
        def sectors(self):
            return []
        def pool(self, *a):
            pytest.fail("缺少报价日期时不请求股票池")
    monkeypatch.setattr(radar, "LiveDataProvider", Provider)
    monkeypatch.setattr(radar, "fetch_quotes", lambda *a: {"quotes": []})
    monkeypatch.setattr(radar, "fetch_daily", lambda *a: (_ for _ in ()).throw(ValueError()))
    result = radar.fetch_radar(load_config())
    assert result["data_date"] is None
    assert result["sentiment"]["limit_up"] is None


def test_radar_cache_is_a_copy(monkeypatch):
    monkeypatch.setattr(radar, "_cache", {})
    calls = []
    monkeypatch.setattr(radar, "fetch_radar", lambda cfg: calls.append(True) or {"feeds": {"test": {"status": "正常"}}})
    first = radar.radar()
    first["feeds"]["test"]["status"] = "已修改"
    assert radar.radar()["feeds"]["test"]["status"] == "正常"
    assert len(calls) == 1
