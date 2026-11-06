"""真实公开行情适配：腾讯指数/分时、东方财富板块与涨跌停池。

各数据集独立标注状态；没有供应商时间戳的股票池不宣称秒级实时。
采集快照存入本机 SQLite，未观测到的历史不回填。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo
import copy
import json
import math
import re
import sqlite3

import httpx

TZ = ZoneInfo("Asia/Shanghai")
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cycle" / "live.sqlite"
_cache = {}
_lock = Lock()


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def parse_quotes(text):
    quotes = []
    for symbol, raw in re.findall(r'v_(\w+)="([^"]*)"', text):
        fields = raw.split("~")
        if len(fields) < 38 or not fields[30]:
            continue
        try:
            timestamp = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
        except ValueError:
            continue
        quotes.append(dict(symbol=symbol, name=fields[1], price=number(fields[3]), pct=number(fields[32]), high=number(fields[33]), low=number(fields[34]), amount=number(fields[37]), timestamp=timestamp.isoformat()))
    if not quotes or any(q["price"] is None or q["pct"] is None for q in quotes):
        raise ValueError("腾讯指数行情字段缺失")
    return quotes


def parse_pool(payload, date):
    data = payload.get("data")
    if not isinstance(data, dict) or str(data.get("qdate")) != date:
        raise ValueError("股票池日期缺失或与指数日期不符")
    rows = data.get("pool")
    if not isinstance(rows, list) or int(data.get("tc", -1)) != len(rows):
        raise ValueError("股票池未完整返回，不能计算全池统计")
    return rows


def hhmm(value):
    value = str(value or "").zfill(6)
    return f"{value[:2]}:{value[2:4]}" if value != "000000" else None


def leader_rows(pool):
    result = []
    for row in pool:
        amount, fund = number(row.get("amount")), number(row.get("fund"))
        result.append(dict(symbol=str(row["c"]).zfill(6), name=row["n"], sector=row.get("hybk", "未提供"), boards=int(row.get("lbc", 0)), pct=number(row.get("zdp")), first_limit_time=hhmm(row.get("fbt")), last_limit_time=hhmm(row.get("lbt")), seal_ratio=fund/amount if fund is not None and amount else None, breaks=row.get("zbc")))
    return sorted(result, key=lambda r: (-r["boards"], r["first_limit_time"] or "99:99", -(r["seal_ratio"] or 0), r["breaks"] or 0, r["symbol"]))


def parse_tencent_minutes(payload, code, name, expected_date):
    data = payload.get("data", {}).get(code, {}).get("data", {})
    if data.get("date") != expected_date:
        raise ValueError(f"{name}分时日期不符")
    points = []
    for raw in data.get("data", []):
        fields = raw.split()
        if len(fields) < 2 or number(fields[1]) is None:
            continue
        time = f"{fields[0][:2]}:{fields[0][2:4]}"
        date = f"{expected_date[:4]}-{expected_date[4:6]}-{expected_date[6:]}"
        points.append(dict(time=time, symbol=code, name=name, price=number(fields[1]), available_at=f"{date}T{time}:00+08:00"))
    if not points:
        raise ValueError(f"{name}没有可用分时")
    return points


def store_snapshot(snapshot, fetched_at, path=DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as db:
        db.execute("CREATE TABLE IF NOT EXISTS snapshots (observed_at TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO snapshots VALUES (?, ?)", (fetched_at, json.dumps(snapshot, ensure_ascii=False, allow_nan=False)))


def read_history(limit, cutoff=None, path=DB_PATH):
    if not path.exists():
        return []
    with sqlite3.connect(path, timeout=10) as db:
        query = "SELECT observed_at,payload FROM snapshots"
        args = []
        if cutoff:
            query += " WHERE observed_at <= ?"
            args.append(cutoff)
        query += " ORDER BY observed_at DESC LIMIT ?"
        args.append(limit)
        rows = db.execute(query, args).fetchall()
    return [dict(json.loads(payload), observed_at=stamp) for stamp, payload in reversed(rows)]


class LiveDataProvider:
    def __init__(self, config, transport=None):
        self.config = config
        # 公开行情直连；不修改进程或用户代理设置。
        self.client = httpx.Client(timeout=config["live_timeout_seconds"], trust_env=False, transport=transport, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})

    def json(self, url, params):
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def pool(self, endpoint, date):
        sort = "fund:asc" if endpoint == "getTopicDTPool" else "zs:desc" if endpoint == "getYesterdayZTPool" else "fbt:asc"
        return parse_pool(self.json(f"https://push2ex.eastmoney.com/{endpoint}", dict(ut="7eea3edcaed734bea9cbfc24409ed989", dpt="wz.ztzt", Pageindex=0, pagesize=self.config["live_pool_page_size"], sort=sort, date=date)), date)

    def sectors(self):
        result = []
        total = None
        for page in range(1, self.config["live_max_sector_pages"]+1):
            payload = self.json("https://push2.eastmoney.com/api/qt/clist/get", dict(pn=page, pz=self.config["live_sector_page_size"], po=1, np=1, fltt=2, fid="f12", fs="m:90 t:2 f:!50", fields="f12,f14,f2,f3,f124"))
            data = payload.get("data")
            if not data:
                raise ValueError("行业板块接口未返回数据")
            total = data["total"]
            rows = data.get("diff", [])
            result.extend(rows.values() if isinstance(rows, dict) else rows)
            if len(result) >= total:
                break
        unique = {r["f12"]: r for r in result}
        if len(unique) != total:
            raise ValueError("行业板块分页不完整")
        return list(unique.values())

    def minutes(self, code, name, date):
        return parse_tencent_minutes(self.json("https://web.ifzq.gtimg.cn/appstock/app/minute/query", {"code": code}), code, name, date)

    def sector_minutes(self, sector, date):
        payload = self.json("https://push2his.eastmoney.com/api/qt/stock/trends2/get", dict(secid="90."+sector["code"], fields1="f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11", fields2="f51,f52,f53,f54,f55,f56,f57,f58", ndays=1, iscr=0))
        rows = (payload.get("data") or {}).get("trends", [])
        result = []
        for raw in rows:
            fields = raw.split(",")
            if fields[0][:10].replace("-", "") == date and number(fields[2]) is not None:
                result.append(dict(time=fields[0][11:16], available_at=fields[0].replace(" ", "T")+":00+08:00", symbol=sector["code"], name=sector["name"], price=number(fields[2])))
        if not result:
            raise ValueError("板块分时为空或日期不符")
        return result

    def fetch(self):
        try:
            response = self.client.get("https://qt.gtimg.cn/q=sh000001,sz399001,sz399006")
            response.raise_for_status()
            quotes = parse_quotes(response.content.decode("gb18030", errors="replace"))
            quote = next(q for q in quotes if q["symbol"] == "sh000001")
            date = quote["timestamp"][:10]
            compact = date.replace("-", "")
            fetched = datetime.now(TZ)
            warnings, feeds, values = [], {}, {}
            tasks = {"涨停池": lambda: self.pool("getTopicZTPool", compact), "跌停池": lambda: self.pool("getTopicDTPool", compact), "炸板池": lambda: self.pool("getTopicZBPool", compact), "昨日涨停池": lambda: self.pool("getYesterdayZTPool", compact), "行业板块": self.sectors}
            with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                futures = {name: executor.submit(fn) for name, fn in tasks.items()}
                for name, future in futures.items():
                    try:
                        values[name] = future.result()
                        feeds[name] = dict(status="正常", count=len(values[name]), data_date=date, provider_time=None, fetched_at=datetime.now(TZ).isoformat())
                    except Exception as exc:
                        values[name] = None
                        feeds[name] = dict(status="不可用", error=str(exc)[:180], data_date=None, provider_time=None)
                        warnings.append(f"{name}不可用，相关字段留空")
            up, down, broken, yesterday = (values[n] for n in ("涨停池", "跌停池", "炸板池", "昨日涨停池"))
            leaders = leader_rows(up or [])
            sectors = []
            for row in values["行业板块"] or []:
                stamp = number(row.get("f124"))
                timestamp = datetime.fromtimestamp(stamp, TZ) if stamp else None
                if timestamp and timestamp.date().isoformat() != date:
                    continue
                members = [r for r in up or [] if r.get("hybk") == row["f14"]]
                first = min((hhmm(r.get("fbt")) for r in members if hhmm(r.get("fbt"))), default=None)
                change = number(row.get("f3"))
                checks = {"板块涨幅达标": change >= self.config["sector_start_pct"] if change is not None else None, "涨停家数达标": len(members) >= self.config["sector_start_limit_up_count"] if up is not None else None, "启动时间达标": first <= self.config["sector_start_before_time"] if first else None}
                sectors.append(dict(code=row["f12"], name=row["f14"], pct=change, limit_up=len(members) if up is not None else None, first_time=first, checks=checks, started=all(v is True for v in checks.values()), provider_time=timestamp.isoformat() if timestamp else None))
            sectors.sort(key=lambda s: (not s["started"], -(s["pct"] if s["pct"] is not None else -1000)))
            attempts = len(up)+len(broken) if up is not None and broken is not None else None
            break_rate = len(broken)/attempts if attempts else 0 if attempts == 0 else None
            down_count, up_count = len(down) if down is not None else None, len(up) if up is not None else None
            previous_returns = [number(r.get("zdp")) for r in yesterday or []]
            previous_returns = [n for n in previous_returns if n is not None]
            mean = sum(previous_returns)/len(previous_returns) if previous_returns else None
            high_risk = down_count is not None and down_count >= self.config["risk_limit_down_count"]
            # 没有昨日同口径快照时，不计算跌停增量与高度断板。
            if any(values[n] is None for n in ("涨停池", "跌停池", "炸板池")):
                state = "数据不足"
            elif high_risk:
                state = "退潮"
            elif up_count <= self.config["ice_limit_up_count"] and quote["pct"] < 0:
                state = "冰点"
            elif break_rate is not None and break_rate >= self.config["break_rate_risk"]:
                state = "分歧"
            elif any(s["started"] for s in sectors):
                state = "启动"
            else:
                state = "待确认"
            minutes = []
            minute_tasks = [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]
            if leaders:
                lead = leaders[0]
                code = ("sh" if lead["symbol"].startswith("6") else "bj" if lead["symbol"].startswith(("4", "8", "9")) else "sz")+lead["symbol"]
                minute_tasks.append((code, lead["name"]))
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [(name, executor.submit(self.minutes, code, name, compact)) for code, name in minute_tasks]
                futures += [(s["name"], executor.submit(self.sector_minutes, s, compact)) for s in sectors[:self.config["live_sector_chart_count"]]]
                for name, future in futures:
                    try:
                        points = future.result()
                        minutes.extend(points)
                        feeds[name+"分时"] = dict(status="正常", count=len(points), provider_time=points[-1]["available_at"])
                    except Exception as exc:
                        feeds[name+"分时"] = dict(status="不可用", error=str(exc)[:180], provider_time=None)
                        warnings.append(name+"分时不可用")
            all_amounts = [q["amount"] for q in quotes if q["symbol"] in ("sh000001", "sz399001") and q["timestamp"][:10] == date]
            snapshot = dict(date=date, available_at=datetime.now(TZ).isoformat(), state=state, market_close=quote["price"], market_low=quote["low"], market_pct=quote["pct"], market_amount=sum(all_amounts)/10000 if len(all_amounts) == 2 and all(n is not None for n in all_amounts) else None,
                new_low=None, limit_up=up_count, limit_down=down_count, height=max((r["boards"] for r in leaders), default=0) if up is not None else None, break_rate=break_rate, seal_rate=len(up)/attempts if attempts else 0 if attempts == 0 else None, yesterday_pct=mean, risk="高" if high_risk else "待核实" if state == "数据不足" else "关注", sectors=sectors[:18], leaders=leaders[:12],
                card=dict(pattern={"启动":"启动龙头", "退潮":"退潮回避", "冰点":"冰点龙头", "分歧":"冲高回落风险"}.get(state,"持续观察"), state=state, action="回避" if high_risk else "观察", checks={"板块启动": any(s["started"] for s in sectors) if sectors else None, "跌停数低于风险阈值": not high_risk if down_count is not None else None, "昨日涨停表现为正": mean > 0 if mean is not None else None}, invalidation="跌停扩散、板块启动条件消失或数据过期时重新核实。", risk="盘中候选，不代表收盘确认；股票池无秒级供应商时间戳。"), rule_version=self.config["rule_version"])
            fetched = datetime.now(TZ)
            metadata = dict(provider="腾讯公开行情 / 东方财富公开行情", fetched_at=fetched.isoformat(), quote_time=quote["timestamp"], refresh_seconds=self.config["live_refresh_seconds"], feeds=feeds, warnings=warnings + ["股票池仅有数据日期，秒级延迟未知；行业名称精确匹配，分类不一致可能低估板块涨停家数。", "仅展示已采集的真实历史；未接入历史成分和完整日线，真实行情回测暂不可用。"], indices=quotes)
            store_snapshot(snapshot, fetched.isoformat())
            return dict(source="akshare", simulated=False, config=self.config, dates=[date], current=snapshot, history=read_history(self.config["live_history_limit"]), intraday=minutes, metadata=metadata,
                backtest=dict(events=[], summary=dict(samples=0,signals=0,win_rate=None,mean=None,median=None), simulation=dict(trades=[],curve=[],max_drawdown=None,final_equity=None)))
        finally:
            self.client.close()


def live_dashboard(config, as_of=None):
    if as_of:
        raise ValueError("真实行情入口仅显示当前快照；历史回放请使用已采集快照或CSV，不使用当前数据补历史")
    key = json.dumps(config, sort_keys=True)
    with _lock:
        if key in _cache and monotonic()-_cache[key][0] < config["live_cache_seconds"]:
            result = copy.deepcopy(_cache[key][1])
        else:
            result = LiveDataProvider(config).fetch()
            _cache.clear()
            _cache[key] = (monotonic(), copy.deepcopy(result))
    stamp = datetime.fromisoformat(result["metadata"]["quote_time"])
    now = datetime.now(TZ)
    age = max(0, int((now-stamp).total_seconds()))
    result["metadata"]["quote_age_seconds"] = age
    result["metadata"]["session"] = "盘中时段" if now.weekday() < 5 and ("09:30" <= now.strftime("%H:%M") <= "11:30" or "13:00" <= now.strftime("%H:%M") <= "15:00") else "非连续交易时段"
    result["metadata"]["stale"] = result["metadata"]["session"] == "盘中时段" and age > config["live_stale_seconds"]
    if result["metadata"]["stale"]:
        result["current"]["state"] = "行情过期"
        result["current"]["card"]["state"] = "行情过期"
        result["current"]["card"]["pattern"] = "持续观察"
        result["current"]["card"]["action"] = "观察"
    return result
