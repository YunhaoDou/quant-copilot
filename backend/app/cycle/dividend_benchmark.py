"""中债十年期国债到期收益率，按股票扫描日可得时间对齐。"""
from datetime import date, timedelta
import re

from app.cycle.live import number

CURVE_URL = "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery"


def parse_benchmark(html, cutoff):
    yields = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.I | re.S):
        cells = [text.strip() for text in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.I | re.S)]
        # gjqx=10 时只保留十年列。列布局或源标签变化时拒绝推断。
        if len(cells) != 10 or cells[0] != "中债国债收益率曲线" or any(cells[2:8]) or cells[9]:
            continue
        try:
            observed = date.fromisoformat(cells[1])
        except ValueError:
            continue
        rate = number(cells[8])
        if observed <= cutoff and rate is not None:
            yields[observed] = rate
    if not yields:
        raise ValueError("中债曲线未返回可验证的十年期记录")
    latest = max(yields)
    if (cutoff - latest).days > 10:
        raise ValueError("中债曲线最近记录已过期")
    previous = max((d for d in yields if d <= latest - timedelta(days=20)), default=None)
    return {
        "date": latest.isoformat(), "yieldPct": yields[latest],
        "previousDate": previous.isoformat() if previous else None,
        "changeBp": round((yields[latest] - yields[previous]) * 100, 2) if previous else None,
    }


def fetch_benchmark(client, stock_date):
    # 收益率曲线日终发布，股票收盘时只比较此前已发布的曲线。
    cutoff = date.fromisoformat(stock_date) - timedelta(days=1)
    response = client.get(CURVE_URL, params={
        "startDate": (cutoff - timedelta(days=35)).isoformat(), "endDate": cutoff.isoformat(),
        "gjqx": 10, "locale": "cn_ZH", "qxId": "ycqx",
    })
    response.raise_for_status()
    return parse_benchmark(response.text, cutoff)
