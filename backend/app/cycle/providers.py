"""可替换数据源；模拟数据仅用于演示程序，不代表真实市场。"""
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd


class DataProvider(ABC):
    @abstractmethod
    def daily(self) -> pd.DataFrame:
        """每行是股票在收盘时可得的快照。"""

    @abstractmethod
    def intraday(self, date: str) -> pd.DataFrame:
        """返回当日分时数据。"""

    def get_market_daily(self, start, end):
        return self.daily().query("@start <= date <= @end").groupby("date", as_index=False).first()

    def get_stock_daily(self, start, end):
        return self.daily().query("@start <= date <= @end")

    def get_sector_daily(self, start, end):
        return self.get_stock_daily(start, end).groupby(["date", "sector"], as_index=False).agg(pct=("pct", "mean"))

    def get_market_intraday(self, date):
        return self.intraday(date).query("symbol == 'INDEX'")

    def get_sector_intraday(self, date):
        return self.intraday(date).query("symbol.str.startswith('SECTOR')", engine="python")

    def get_limit_up_pool(self, date):
        return self.daily().query("date == @date and close >= upper_limit")

    def get_limit_down_pool(self, date):
        return self.daily().query("date == @date and close <= lower_limit")

    def get_sector_members(self, sector):
        return self.daily().query("sector == @sector")[["symbol", "name"]].drop_duplicates()


class MockDataProvider(DataProvider):
    def __init__(self, seed=42, days=120):
        rng = np.random.default_rng(seed)
        rows = []
        prices = np.full(18, 20.0)
        heights = np.zeros(18, dtype=int)
        index = 3200.0
        for day, date in enumerate(pd.bdate_range("2026-01-05", periods=days)):
            phase = day % 12
            market_pct = [-1.7, -1.1, -.6, .4, 1.2, .8, -.5, .7, -.8, -1.6, .2, .5][phase]
            index *= 1 + market_pct / 100
            for j in range(18):
                prev = prices[j]
                upper, lower = round(prev * 1.1, 2), round(prev * .9, 2)
                lead = j % 6 == 0
                pct = float(rng.normal(market_pct, 2))
                if (lead and phase in (2, 3, 4, 5, 7)) or (j % 6 < 3 and phase == 3):
                    close = upper
                elif phase == 9 and j % 2 == 0:
                    close = lower
                else:
                    close = round(np.clip(prev * (1 + pct / 100), lower, upper), 2)
                heights[j] = heights[j] + 1 if close == upper else 0
                opened = round(prev * (1 + market_pct / 200), 2)
                # 专门构造不可成交样本。
                locked = lead and phase == 4
                opened = close if locked else opened
                high = close if locked else max(opened, close, round(prev * 1.03, 2))
                low = close if locked else min(opened, close, round(prev * .98, 2))
                rows.append(dict(date=date.strftime("%Y-%m-%d"), available_at=date.strftime("%Y-%m-%d") + "T15:00:00+08:00",
                    symbol=f"{600001+j:06d}", name=f"模拟标的{j+1:02d}", sector=["算力示例", "机器人示例", "新能源示例"][j//6],
                    open=opened, high=high, low=low, close=close, pct=round((close/prev-1)*100, 2),
                    upper_limit=upper, lower_limit=lower, volume=int(rng.integers(100000, 900000)),
                    amount=round(close*500000, 2), boards=int(heights[j]), first_limit_time="09:35" if lead else "10:15",
                    seal_ratio=round(float(rng.uniform(.02, .3)), 3), breaks=int(rng.integers(1, 4)) if phase in (6, 8) else 0,
                    market_close=round(index, 2), market_low=round(index*.995, 2), market_pct=market_pct,
                    market_amount=round(float(rng.uniform(7000, 14000)), 1), suspended=False))
                prices[j] = close
        self.frame = pd.DataFrame(rows)

    def daily(self):
        return self.frame.copy()

    def intraday(self, date):
        current = self.frame[self.frame.date == date]
        if current.empty:
            return pd.DataFrame()
        rows = []
        times = list(pd.date_range(f"{date} 09:35", f"{date} 11:30", freq="5min")) + list(pd.date_range(f"{date} 13:05", f"{date} 15:00", freq="5min"))
        assets = [("INDEX", "大盘示例", float(current.iloc[0].market_close), float(current.iloc[0].market_pct))]
        assets += [(r.symbol, r.name, r.close, r.pct) for r in current.itertuples()]
        assets += [(f"SECTOR{i}", sector, 100.0, float(group.pct.mean())) for i, (sector, group) in enumerate(current.groupby("sector"))]
        for symbol, name, close, pct in assets:
            start = close/(1+pct/100)
            for i, time in enumerate(times):
                price = start + (close-start)*(i+1)/len(times) + start*.002*np.sin(i*.5)
                rows.append(dict(time=time.strftime("%H:%M"), available_at=time.isoformat()+"+08:00", symbol=symbol, name=name, price=round(price, 3), volume=10000, amount=price*10000))
        return pd.DataFrame(rows)


class CSVDataProvider(DataProvider):
    def __init__(self, root: Path):
        self.root = root

    def daily(self):
        frame = pd.read_csv(self.root / "daily.csv", dtype={"symbol": str})
        required = set(MockDataProvider(days=1).daily().columns)
        missing = required - set(frame.columns)
        if missing:
            raise ValueError("CSV 缺少字段：" + ", ".join(sorted(missing)))
        if frame.duplicated(["date", "symbol"]).any():
            raise ValueError("CSV 存在重复日期与代码")
        numeric = list(required - {"date", "available_at", "symbol", "name", "sector", "first_limit_time", "suspended"})
        frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
        if frame[numeric].isna().any().any() or not np.isfinite(frame[numeric]).all().all():
            raise ValueError("CSV 数值字段存在缺失或无穷值")
        if not frame.suspended.isin([True, False, 0, 1]).all():
            raise ValueError("suspended 必须为布尔值")
        pd.to_datetime(frame.available_at, utc=True, errors="raise")
        return frame.sort_values(["date", "symbol"])

    def intraday(self, date):
        frame = pd.read_csv(self.root / "intraday.csv", dtype={"symbol": str})
        return frame[frame.available_at.str.startswith(date)]


class AkShareDataProvider(DataProvider):
    def snapshot(self):
        from app.cycle.engine import load_config
        from app.cycle.live import live_dashboard
        return live_dashboard(load_config())

    def daily(self):
        raise ValueError("真实快照不提供伪造历史日线，请使用snapshot接口或已验证的个股日线接口")

    def intraday(self, date):
        payload = self.snapshot()
        if payload["current"]["date"] != date:
            raise ValueError("真实分钟接口当前只提供最新行情日")
        return pd.DataFrame(payload["intraday"])
