"""真实日线的缓存必须跨收盘边界重新获取，且不让盘中未完成K线进入回测。

同时覆盖腾讯报价的唯一抓取+解析实现（market.parse_quotes/fetch_quote_rows/fetch_quotes），
它是全项目报价消费方和 cycle/live.py 指数看板共用的那一份。
"""
from datetime import datetime

import httpx

from app.cycle import market


def quote_text(code="sh600519", fields=47, **overrides):
    values = {
        1: "贵州茅台", 2: "600519", 3: "1500", 4: "1480", 5: "1490",
        30: "20261106150000", 32: "1.35", 33: "1520", 34: "1470",
        37: "123456", 39: "30.5", 46: "8.2",
    }
    values.update({int(index.lstrip("f")): value for index, value in overrides.items()})
    rows = ["0"] * fields
    for index, value in values.items():
        if index < fields:
            rows[index] = value
    return f'v_{code}="' + "~".join(rows) + '";'


def test_parse_quotes_uses_strict_field_guard_and_yuan_units():
    # 46 个字段不满足 PE/PB 所需下标，直接跳过，不再退回旧的 >=38 宽松档。
    assert market.parse_quotes(quote_text(fields=46)) == []
    rows = market.parse_quotes(quote_text())
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "sh600519" and row["name"] == "贵州茅台"
    assert row["price"] == 1500 and row["previous_close"] == 1480 and row["open"] == 1490
    assert row["pct"] == 1.35 and row["pe"] == 30.5 and row["pb"] == 8.2
    # 供应商 f37 单位是万元，解析后 amount_yuan 统一为元。
    assert row["amount_yuan"] == 123456 * 10000
    assert row["volume_lots"] == 0
    assert row["quote_time"] == "2026-11-06T15:00:00+08:00"


def test_parse_quotes_keeps_fund_pe_pb_empty_but_parses_row():
    row = market.parse_quotes(quote_text(code="sh510300"))[0]
    assert row["pe"] is None and row["pb"] is None
    assert row["amount_yuan"] == 123456 * 10000


def test_fetch_quotes_payload_still_feeds_downstream_consumers(monkeypatch):
    calls = []

    def respond(request):
        calls.append(str(request.url))
        assert "qt.gtimg.cn" in str(request.url)  # codes live in the path, not a query param
        return httpx.Response(200, content=quote_text().encode("gb18030"))

    real_client = httpx.Client
    monkeypatch.setattr(market, "_cache", {})
    monkeypatch.setattr(
        market.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    payload = market.fetch_quotes(["600519", "000001"])
    assert payload["provider"] == "腾讯公开行情"
    assert payload["missing"] == ["sz000001"]
    quote = payload["quotes"][0]
    # 下游（paper_trading/research_lab/trend_leader/radar）依赖的字段全部保留。
    for field in ("symbol", "code", "name", "price", "previous_close", "open", "high", "low",
                  "pct", "pe", "pb", "volume_lots", "amount_yuan", "quote_time", "currency"):
        assert field in quote
    assert len(calls) == 1
    # 第二次命中 market 报价缓存，不再请求上游。
    assert market.fetch_quotes(["600519", "000001"])["quotes"][0]["price"] == 1500
    assert len(calls) == 1


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
