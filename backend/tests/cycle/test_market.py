"""真实日线的缓存必须跨收盘边界重新获取，且不让盘中未完成K线进入回测。"""
from datetime import datetime

import httpx

from app.cycle import market


def test_daily_cache_reloads_at_close_without_incomplete_bar(monkeypatch):
    class Clock(datetime):
        hour_value = 14

        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 6, cls.hour_value, 30, tzinfo=market.TZ)

    calls = []

    def respond(request):
        calls.append(request.url)
        return httpx.Response(200, json={"data": {"sh600519": {"qfqday": [
            ["2026-11-05", "10", "11", "12", "9", "100"],
            ["2026-11-06", "11", "12", "13", "10", "200"],
        ]}}})

    client = httpx.Client
    monkeypatch.setattr(market, "datetime", Clock)
    monkeypatch.setattr(market, "_daily_cache", {})
    monkeypatch.setattr(market.httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(respond)))
    assert market.fetch_daily("600519").trade_date.tolist() == ["2026-11-05"]
    assert market.fetch_daily("600519").trade_date.tolist() == ["2026-11-05"]
    assert len(calls) == 1
    Clock.hour_value = 15
    assert market.fetch_daily("600519").trade_date.tolist() == ["2026-11-05", "2026-11-06"]
    assert len(calls) == 2
    assert all(url.path.endswith("/newfqkline/get") for url in calls)
