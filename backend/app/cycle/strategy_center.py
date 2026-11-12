"""可解释的研究策略和独立影子账户，共用保守报价撮合。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from threading import Lock

from fastapi import APIRouter, HTTPException
import numpy as np

from app.cycle.engine import load_config
from app.cycle.events import database, encode
from app.cycle.live import TZ, number
from app.cycle.market import fetch_daily, fetch_quotes
from app.cycle.strategy_sim import new_account, log, step

router = APIRouter(prefix="/strategy-center", tags=["策略研究"])
_executor = ThreadPoolExecutor(max_workers=1)
_lock = Lock()
_refresh = {"state": "尚未核验", "updated_at": None, "error": None}
CATALOG = [
    {"id": "quality-value", "name": "质量价值", "logic": "用持续盈利和现金覆盖筛公司，再约束支付价格。",
     "evidence": "价值因子有中国市场实证研究；本页具体门槛是待验证的工程规则。",
     "entry": "非金融股财务证据支持、动态PE和PB为正且低于配置上限、经营现金流与利润匹配。",
     "exit": "估值或财务门槛失效，或触发共用价格止损、止盈及回撤线。",
     "source": "https://www.nber.org/papers/w24458"},
    {"id": "dividend-cash", "name": "红利现金流", "logic": "比较可持续派息、现金流覆盖和买入收益率。",
     "evidence": "借鉴红利指数筛选和现金分红研究；具体阈值需独立检验。",
     "entry": "连续派息、股息率、同财年派息率、自由现金流覆盖、现金利润比及股债差全部满足。",
     "exit": "已核验分红或财务门槛失效，或触发共用风险退出。",
     "source": "https://www.csrc.gov.cn/csrc/c101954/c7449656/content.shtml"},
    {"id": "dividend-lowvol", "name": "红利低波", "logic": "在现金流支持的红利候选中限制价格波动。",
     "evidence": "指数机构研究支持组合研究方向，本页波动门槛及单仓撮合仍需检验。",
     "entry": "先满足红利现金流规则，再要求前置60日收益年化波动不高于配置上限。",
     "exit": "红利门槛失效、波动超过上限，或触发共用风险退出。",
     "source": "https://www.spglobal.com/spdji/zh/education/article/talkingpoints-finding-resilience-amid-uncertainty-a-low-volatility-high-dividend-approach-for-the-a-share-market/"},
    {"id": "fundamental-trend", "name": "基本面改善后趋势入场", "logic": "让可核验盈利改善与价格趋势同时出现。",
     "evidence": "复合研究假设。当前盈利改善按年报扣非利润同比核验，季度经营变化需补充。",
     "entry": "非金融财务证据支持、年报扣非利润同比达到配置增速、价格高于20日均线且20日均线高于60日均线。",
     "exit": "盈利或趋势条件失效，或触发共用风险退出。"},
    {"id": "relative-trend", "name": "相对强势趋势", "logic": "观察相对宽基走强、突破且有趋势延续的候选。",
     "evidence": "中国市场动量证据依赖期限和样本；本页规则为待验证假设。",
     "entry": "价格超过前20日收盘高点、20日均线高于60日均线，60日收益跑赢沪深300ETF至少配置百分点。",
     "exit": "价格跌回趋势或相对强势门槛失效，或触发共用风险退出。",
     "source": "https://www.sciencedirect.com/science/article/pii/S1059056018301928"},
    {"id": "leader-rebound", "name": "情绪龙头回补", "logic": "沿板块启动、分歧、回补的证据推进。",
     "evidence": "用户提出的待验证事件策略，沿用已启动账户与原始记录。",
     "entry": "见情绪周期策略模拟的市场、阶段及可成交规则。", "exit": "见现有策略的阶段窗口及风险退出。"},
]

# 五个财务/趋势账户保留原候选池与独立更新逻辑。
RESEARCH_CATALOG = CATALOG[:-1]
CATALOG.append({"id":"trend-leader-band","name":"主线趋势中军波段",
    "logic":"第七策略：主线持续性 → 趋势中军 → 缩量回踩与次日确认 → 结构退出 → 风险预算。",
    "evidence":"严格规则的前向模拟，尚无策略有效性结论；缺失资金和主线证据时等待。",
    "entry":"最接近相对强势趋势，但要求主线、多日梯队、中军地位及缩量回踩确认；不追连板。",
    "exit":"固定5%止损、收盘跌破20日线或退潮信号；REDUCE首版保守退出全部单仓。"})


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS research_strategy_accounts (
        strategy_id TEXT PRIMARY KEY, payload TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS research_strategy_signals (
        strategy_id TEXT PRIMARY KEY, payload TEXT NOT NULL)""")


def load(db, name, table="research_strategy_accounts"):
    schema(db)
    row = db.execute(f"SELECT payload FROM {table} WHERE strategy_id=?", (name,)).fetchone()
    return json.loads(row[0]) if row else None


def persist(db, name, value, table="research_strategy_accounts"):
    db.execute(f"INSERT OR REPLACE INTO {table} VALUES(?,?)", (name, encode(value)))


def check(label, value, lower=None, upper=None):
    value = number(value)
    return {"label": label, "value": value, "minimum": lower, "maximum": upper,
            "passed": None if value is None else (lower is None or value >= lower) and (upper is None or value <= upper)}


def evaluate(strategy_id, stock, quote, metrics, benchmark, config):
    quality = stock.get("quality") or {}
    financial = quality.get("financialIndustry") is True
    baseline = stock.get("historicalCashPerShare")
    price = quote["price"]
    import re
    checks = [{"label":"非风险警示、退市或新股特殊交易阶段", "passed":not any(re.search(r"ST|退|^[NC]", name, re.I) for name in (stock.get("name", ""), quote.get("name", "")))}]
    if strategy_id != "relative-trend":
        tier = quality.get("financialEvidenceStatus",quality.get("status")) if strategy_id in ("quality-value","fundamental-trend") else quality.get("status")
        checks.append({"label": "非金融财务证据支持", "passed": None if not quality or tier in (None,"unknown") else tier == "supported" and not financial})
    if strategy_id == "quality-value":
        checks.extend([
            check("动态PE", quote.get("pe"), .01, config["research_value_pe_max"]),
            check("PB", quote.get("pb"), .01, config["research_value_pb_max"]),
            check("现金利润比", quality.get("cashProfitRatio"), config["dividend_screen_cash_profit_min"]),
        ])
    if strategy_id in ("dividend-cash", "dividend-lowvol"):
        rate = number((benchmark or {}).get("yieldPct"))
        spread = baseline/price*100-rate if baseline and rate is not None else None
        checks.extend([
            check("已实施股息率%", stock.get("cashPerShare", 0)/price*100,
                  config["dividend_screen_yield_min_pct"], config["dividend_screen_yield_max_pct"]),
            check("连续派息年数", stock.get("consecutiveYears"), config["dividend_screen_min_years"]),
            check("估算派息率%", quality.get("payoutPct"), config["dividend_screen_payout_min_pct"], config["dividend_screen_payout_max_pct"]),
            check("现金流覆盖", quality.get("fcfCover"), config["dividend_min_fcf_cover"]),
            check("经营现金覆盖", quality.get("ocfCover"), config["dividend_screen_ocf_cover_min"]),
            check("现金利润比", quality.get("cashProfitRatio"), config["dividend_screen_cash_profit_min"]),
            check("历史中位股息率减国债百分点", spread, config["dividend_screen_spread_min_pp"]),
        ])
        if strategy_id == "dividend-lowvol":
            checks.append(check("前置60日年化波动%", metrics.get("volatility"), 0, config["research_volatility_max_pct"]))
    if strategy_id == "fundamental-trend":
        profits = quality.get("deductedProfits") or []
        growth = (profits[0]/profits[1]-1)*100 if len(profits) >= 2 and profits[0] is not None and profits[1] and profits[1] > 0 else None
        checks.append(check("年报扣非利润同比%", growth, config["research_profit_growth_min_pct"]))
    if strategy_id in ("fundamental-trend", "relative-trend"):
        ma20, ma60 = metrics.get("ma20"), metrics.get("ma60")
        checks.extend([
            check("价格相对20日均线%", (price/ma20-1)*100 if ma20 else None, 0),
            check("20日均线相对60日均线%", (ma20/ma60-1)*100 if ma20 and ma60 else None, 0),
        ])
    if strategy_id == "relative-trend":
        high, base = metrics.get("high20"), metrics.get("return_base")
        relative = (price/base-1)*100 - metrics["benchmark_return"] if base and metrics.get("benchmark_return") is not None else None
        checks.extend([
            check("相对前20日收盘高点%", (price/high-1)*100 if high else None, .000001),
            check("60日跑赢宽基百分点", relative, config["research_relative_min_pp"]),
        ])
    failed = any(row["passed"] is False for row in checks)
    unknown = any(row["passed"] is None for row in checks)
    hold_checks = [row for row in checks if row["label"] != "相对前20日收盘高点%"]
    values = {row["label"]: row.get("value") for row in checks}
    rank_value = {
        "quality-value": quote.get("pe"),
        "dividend-cash": -(baseline/price*100) if baseline else None,
        "dividend-lowvol": metrics.get("volatility"),
        "fundamental-trend": -values["年报扣非利润同比%"] if values.get("年报扣非利润同比%") is not None else None,
        "relative-trend": -values["60日跑赢宽基百分点"] if values.get("60日跑赢宽基百分点") is not None else None,
    }[strategy_id]
    return {"status": "fail" if failed else "unknown" if unknown else "pass", "checks": checks,
            "exit_failed": any(row["passed"] is False for row in hold_checks), "priority": rank_value or 0}


def refresh_signals():
    from app.cycle import all_a
    try:
        config = load_config()
        snapshot = all_a.saved()
        today = datetime.now(TZ).date().isoformat()
        if not snapshot or snapshot.get("tradeDate") != today or snapshot.get("evidence_state") != "财报与分红读取完成":
            snapshot = all_a.refresh()
        stocks = list(snapshot["stocks"])
        _refresh.update(scope="all-a",total=len(stocks),checked=0,state="正在核验全A股日线")
        with database() as db:
            schema(db)
            for spec in RESEARCH_CATALOG:
                account = load(db, spec["id"])
                previous = load(db, spec["id"], "research_strategy_signals")
                if not account or not previous:
                    continue
                needed = {(account.get(key) or {}).get("symbol") for key in ("position", "pending")}
                for stock in previous["stocks"]:
                    if stock["code"] in needed and stock["code"] not in {row["code"] for row in stocks}:
                        stocks.append({**stock, "retained_only": True})
        if not stocks or snapshot.get("scope") != "all-a":
            raise ValueError("完整全A股母池尚未就绪")
        today = datetime.now(TZ).date().isoformat()
        # 财务字段仍有研究时效要求；不把多年旧快照当作当前资格。
        if (datetime.now(TZ).date() - datetime.fromisoformat(snapshot["tradeDate"]).date()).days > config["research_financial_cache_days"]:
            raise ValueError("财务候选快照已过期，请更新红利扫描")
        benchmark = snapshot.get("benchmark")
        if benchmark and (datetime.now(TZ).date()-datetime.fromisoformat(benchmark["date"]).date()).days > config["research_bond_cache_days"]:
            benchmark = None
        base = fetch_daily("510300", 100)
        base = base[base.trade_date < today].sort_values("trade_date").tail(61)
        benchmark_dates = base.trade_date.tolist()
        benchmark_return = (float(base.close.iloc[-1])/float(base.close.iloc[0])-1)*100 if len(base) == 61 else None
        with database() as db:
            db.execute("CREATE TABLE IF NOT EXISTS research_daily_cache (as_of TEXT,symbol TEXT,payload TEXT,PRIMARY KEY(as_of,symbol))")
            allowed={stock["code"] for stock in stocks}
            results={row[0]:json.loads(row[1]) for row in db.execute("SELECT symbol,payload FROM research_daily_cache WHERE as_of=?",(today,)) if row[0] in allowed}
        failures = []
        _refresh.update(checked=len(results))
        def collect(stock):
            frame = fetch_daily(stock["code"], 100)
            frame = frame[frame.trade_date < today].sort_values("trade_date")
            if len(frame) < 61:
                raise ValueError("不足61个前置交易日")
            # 与宽基按相同交易日对齐，缺失或停牌时相对收益保留未知。
            aligned = frame.set_index("trade_date").reindex(benchmark_dates)
            closes = frame.close.astype(float)
            if not np.isfinite(closes).all() or (closes <= 0).any():
                raise ValueError("日线价格含非有限或非正值")
            relative_valid = len(benchmark_dates) == 61 and not aligned.close.isna().any()
            return stock["code"], dict(
                ma20=float(closes.tail(20).mean()), ma60=float(closes.tail(60).mean()),
                high20=float(closes.tail(20).max()),
                volatility=float(closes.tail(61).pct_change().dropna().std(ddof=1)*np.sqrt(252)*100),
                return_base=float(aligned.close.iloc[0]) if relative_valid else None,
                benchmark_return=benchmark_return if relative_valid else None,
                history_through=frame.trade_date.max(),
            )
        with ThreadPoolExecutor(max_workers=config["research_scan_workers"]) as pool:
            tasks = {pool.submit(collect, stock): stock["code"] for stock in stocks if stock["code"] not in results}
            for future in as_completed(tasks):
                try:
                    code, metrics = future.result()
                    results[code] = metrics
                    with database() as db:
                        db.execute("INSERT OR REPLACE INTO research_daily_cache VALUES(?,?,?)",(today,code,encode(metrics)))
                except Exception as exc:
                    failures.append(f"{tasks[future]}：{str(exc)[:120]}")
                _refresh.update(checked=len(results)+len(failures),total=len(stocks))
        now = datetime.now(TZ).isoformat()
        with database() as db:
            schema(db)
            for spec in RESEARCH_CATALOG:
                persist(db, spec["id"], {
                    "scope":"all-a", "generated_at": now, "financial_date": snapshot["tradeDate"], "benchmark": benchmark,
                    "pool_total": len(snapshot["stocks"]), "checked": len(stocks),
                    "stocks": [{**stock, "metrics": results.get(stock["code"], {})} for stock in stocks],
                    "failures": failures,
                }, "research_strategy_signals")
        _refresh.update(state="核验完成", updated_at=now, error=None, valid=len(results),failed=len(failures))
        run_accounts()
    except Exception as exc:
        _refresh.update(state="核验失败", error=str(exc)[:200])
    finally:
        _refresh["running"] = False


def enqueue_refresh():
    with _lock:
        if _refresh.get("running"):
            return
        _refresh.update(state="正在核验", error=None, running=True)
        _executor.submit(refresh_signals)


def run_accounts():
    config = load_config()
    with database() as db:
        schema(db)
        packages = [(spec["id"], load(db, spec["id"]), load(db, spec["id"], "research_strategy_signals")) for spec in RESEARCH_CATALOG]
    if any(account and account["status"] == "running" and (not package or package.get("scope") != "all-a") for _,account,package in packages):
        enqueue_refresh()
    symbols = sorted({stock["code"] for _, account, package in packages if account and account["status"] == "running" and package for stock in package["stocks"]})
    if not symbols:
        return
    quotes = {}
    for offset in range(0, len(symbols), 100):
        try:
            quotes.update({q["code"]: q for q in fetch_quotes(symbols[offset:offset+100])["quotes"]})
        except Exception:
            continue
    now = datetime.now(TZ)
    for name, account, package in packages:
        if not account or account["status"] != "running" or not package:
            continue
        signals, candidates = [], []
        package_date = package["generated_at"][:10]
        if package_date != now.date().isoformat():
            enqueue_refresh()
            continue
        for stock in package["stocks"]:
            quote = quotes.get(stock["code"])
            if not quote or not quote.get("price") or quote["price"] <= 0 or quote["quote_time"][:10] != now.date().isoformat():
                continue
            age = (now-datetime.fromisoformat(quote["quote_time"])).total_seconds()
            result = evaluate(name, stock, quote, stock["metrics"], package.get("benchmark"), config)
            candidates.append({"code": stock["code"], "name": stock["name"], "quote_time": quote["quote_time"], **result})
            clock = now.strftime("%H:%M")
            in_session = now.weekday() < 5 and ("09:30" <= clock <= "11:30" or "13:00" <= clock <= "15:00")
            if not in_session or not 0 <= age <= config["live_stale_seconds"]:
                continue
            condition = None if result["status"] == "unknown" or stock.get("retained_only") or package.get("scope") != "all-a" else result["status"] == "pass"
            signals.append({
                "id": f"{name}:{stock['code']}", "status": "active", "stage": "", "dates": [],
                "entry_key": f"{stock['code']}:{quote['quote_time'][:10]}",
                "priority": result["priority"],
                "signal_reason": f"{next(spec['name'] for spec in CATALOG if spec['id']==name)}量化条件满足",
                "first": {"market": {}}, "latest": {
                    "quote_time": quote["quote_time"], "observed_at": now.isoformat(),
                    "exit_failed": result["exit_failed"],
                    "market": {"risk": "关注"}, "sector": {"started": condition},
                    "leaders": [{"symbol": stock["code"]}],
                    "watched": [{"symbol": stock["code"], "quote": quote}],
                },
            })
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            current = load(db, name)
            if not current or current["status"] != "running":
                continue
            current["candidate_count"] = len(candidates)
            current["candidates"] = sorted(candidates,key=lambda c:(c["status"]!="pass",c["priority"],c["code"]))[:config["research_display_limit"]]
            current["data"] = {"scope":package.get("scope","legacy-limited"),**{k: package[k] for k in ("generated_at", "financial_date", "pool_total", "checked", "failures")}}
            previous_trade_count = len(current["trades"])
            entry_scope=(current.get("position") or {}).get("universe_scope","切换全A股之前的原范围")
            previous_position=current.get("position")
            step(current, signals, policy="research")
            for trade in current["trades"][previous_trade_count:]:
                trade["universe_scope"] = ("all-a" if package.get("scope") == "all-a" else "原范围") if trade["side"]=="buy" else ("all-a" if entry_scope=="all-a" else "切换前持仓退出")
            if current.get("position") and not previous_position:
                current["position"]["universe_scope"]=package.get("scope","legacy-limited")
            if not signals:
                log(current, now.isoformat(), "等待新鲜报价，当前为休市或数据不可用")
            elif not current["position"] and not current["pending"]:
                log(current, now.isoformat(), f"本轮核验{len(candidates)}只，满足{sum(c['status']=='pass' for c in candidates)}只。未成交原因见逐项条件和判断日志")
            persist(db, name, current)


@router.get("")
def catalog():
    with database() as db:
        schema(db)
        strategies = [{**spec, "account": load(db, spec["id"]) if spec["id"] != "leader-rebound" else None} for spec in CATALOG]
    progress = dict(_refresh)
    saved_dates = [(spec.get("account") or {}).get("data", {}).get("generated_at") for spec in strategies]
    if not progress["updated_at"] and not progress.get("running") and any(saved_dates):
        saved_data=next(((spec.get("account") or {}).get("data",{}) for spec in strategies if (spec.get("account") or {}).get("data")),{})
        failed=len(saved_data.get("failures",[]))
        progress.update(state="已载入保存的核验", updated_at=max(value for value in saved_dates if value),total=saved_data.get("pool_total",0),checked=saved_data.get("checked",0),failed=failed,valid=max(0,saved_data.get("checked",0)-failed))
    from app.cycle.trend_forward import status as trend_status
    for spec in strategies:
        if spec["id"] == "trend-leader-band":
            spec["account"] = trend_status()["account"]
    from app.cycle.experiment import setup
    from app.cycle import all_a
    universe = all_a.saved()
    return {"experiment":setup(),"market_scan":{**all_a.state,"total":(universe or {}).get("total",0),"evidence_state":(universe or {}).get("evidence_state")},"strategies": strategies, "refresh": progress,
            "universe": "沪深北完整A股母池；各策略按自身条件筛选，未满足条件或证据缺失保持空仓；当前扫描覆盖率见进度"}


@router.post("/start-all")
def start_all():
    config = load_config()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        schema(db)
        for spec in RESEARCH_CATALOG:
            account = load(db, spec["id"]) or new_account(config)
            account["status"] = "running"
            log(account, datetime.now(TZ).isoformat(), "研究策略已启动，等待真实信号与后续可成交报价。当前母池为完整沪深北A股，缺失证据不建仓")
            persist(db, spec["id"], account)
    # 同一情绪账户沿用已有记录。
    from app.cycle.strategy_sim import start
    start()
    from app.cycle.trend_forward import control as trend_control
    trend_control("start")
    enqueue_refresh()
    return catalog()


@router.post("/refresh")
def refresh():
    enqueue_refresh()
    return {"refresh": dict(_refresh)}


@router.post("/{strategy_id}/{action}")
def control(strategy_id: str, action: str):
    if strategy_id not in {spec["id"] for spec in RESEARCH_CATALOG} or action not in ("start", "pause", "exit"):
        raise HTTPException(404, "策略或动作不存在")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        account = load(db, strategy_id)
        if not account:
            account = new_account(load_config())
        if action == "exit":
            position = account["position"]
            account["pending"] = dict(side="sell", symbol=position["symbol"], event_id=position["event_id"],
                                      signal_time=datetime.now(TZ).isoformat(), reason="人工请求退出") if position else None
            account["status"] = "running"
        else:
            account["status"] = "running" if action == "start" else "paused"
        persist(db, strategy_id, account)
    if action == "start":
        enqueue_refresh()
    return {"account": account}
