"""启动—分歧—回补策略的本地影子账户。按后续报价模拟，不接入券商。"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json

from fastapi import APIRouter, HTTPException

from app.cycle.events import database, list_events, encode
from app.cycle.live import TZ

router = APIRouter(prefix="/cycle/strategy-sim", tags=["策略模拟"])


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS strategy_sim (
        id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS strategy_reviews (
        trade_date TEXT PRIMARY KEY, payload TEXT NOT NULL)""")


def read(db):
    schema(db)
    row = db.execute("SELECT payload FROM strategy_sim WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def save(db, account):
    db.execute("INSERT OR REPLACE INTO strategy_sim VALUES(1,?)", (encode(account),))


def new_account(config):
    return {
        "status": "running", "created_at": datetime.now(TZ).isoformat(),
        "capital": config["initial_capital"], "cash": config["initial_capital"],
        "equity": config["initial_capital"], "peak": config["initial_capital"],
        "position": None, "pending": None, "trades": [], "decisions": [],
        "processed": {}, "completed_legs": [], "curve": [],
        "rules": {k: config[k] for k in (
            "position_pct", "buy_cost_bps", "sell_cost_bps", "slippage_bps", "lot_size",
            "sim_stop_loss_pct", "sim_take_profit_pct", "sim_drawdown_limit_pct",
            "sim_start_max_days", "sim_reentry_day", "sim_exit_days",
        )},
    }


def log(account, stamp, text, event_id=None):
    account["decisions"].append({"time": stamp, "event_id": event_id, "text": text})
    account["decisions"] = account["decisions"][-300:]


def price_limit(quote):
    code, previous = quote.get("code", ""), quote.get("previous_close")
    name = quote.get("name", "")
    if not previous or "ST" in name.upper() or "退" in name:
        return None
    pct = .2 if code.startswith(("300", "301", "688", "689")) else .3 if code.startswith(("4", "8", "92")) else .1
    round_price = lambda n: float(Decimal(str(n)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP))
    return round_price(previous * (1-pct)), round_price(previous * (1+pct))


def step(account, events, policy="cycle"):
    """同一行情时点仅处理一次，模拟订单最早在下一可得报价执行。"""
    if account["status"] != "running":
        return account
    rules = account["rules"]
    if policy == "research":
        order = lambda e: (e["latest"].get("observed_at", e["latest"]["quote_time"]), e.get("priority", 0), e["id"])
    else:
        order = lambda e: e["latest"]["quote_time"]
    for event in sorted(events, key=order):
        if event["status"] != "active":
            continue
        latest, first = event["latest"], event["first"]
        stamp = latest["quote_time"]
        if stamp <= account["created_at"] or stamp <= account["processed"].get(event["id"], ""):
            continue
        account["processed"][event["id"]] = stamp
        quotes = {row["symbol"]: row.get("quote") for row in latest.get("watched", [])}
        position = account["position"]
        pending = account["pending"]
        if position and position["event_id"] != event["id"]:
            continue
        if pending and pending["event_id"] != event["id"]:
            continue
        if pending:
            quote = quotes.get(pending["symbol"])
            if quote and quote["quote_time"] > pending["signal_time"] and quote["quote_time"][:10] == stamp[:10]:
                limits = price_limit(quote)
                buy = pending["side"] == "buy"
                price = quote.get("price")
                # 涨停买入、跌停卖出采用不成交假设。
                if not limits or not price or (buy and price >= limits[1]) or (not buy and price <= limits[0]):
                    log(account, stamp, "订单等待：涨跌停、风险警示或价格数据不完整", event["id"])
                elif not buy and quote["quote_time"][:10] <= position["entry_time"][:10]:
                    log(account, stamp, "订单等待：T+1卖出约束", event["id"])
                elif buy and (not latest["sector"].get("started") or latest["market"].get("risk") == "高"
                              or event["stage"] == "退潮回避"):
                    account["pending"] = None
                    log(account, stamp, "取消模拟买单：触发条件消失或风险升高", event["id"])
                else:
                    fill = price * (1 + rules["slippage_bps"]/10000 * (1 if buy else -1))
                    if fill > limits[1] or fill < limits[0]:
                        log(account, stamp, "订单等待：计入滑点后的模拟价格超出涨跌停范围", event["id"])
                        continue
                    if buy:
                        budget = min(account["cash"], account["equity"] * rules["position_pct"]/100)
                        unit = fill * (1+rules["buy_cost_bps"]/10000)
                        quantity = int(budget/unit/rules["lot_size"]) * rules["lot_size"]
                        if quantity <= 0:
                            account["pending"] = None
                            log(account, stamp, "放弃模拟买入：预算不足一手", event["id"])
                            continue
                        cost = quantity*unit
                        account["cash"] -= cost
                        account["position"] = {
                            "event_id": event["id"], "symbol": pending["symbol"], "name": quote["name"],
                            "quantity": quantity, "entry_price": fill, "cost": cost,
                            "entry_time": quote["quote_time"], "mark": price, "mark_time": quote["quote_time"],
                        }
                        account["completed_legs"].append(pending["leg"])
                    else:
                        quantity = position["quantity"]
                        proceeds = quantity*fill*(1-rules["sell_cost_bps"]/10000)
                        account["cash"] += proceeds
                        account["position"] = None
                    account["trades"].append({
                        "time": quote["quote_time"], "side": pending["side"], "symbol": pending["symbol"],
                        "price": fill, "quantity": quantity, "reason": pending["reason"],
                        "pnl": None if buy else proceeds-position["cost"],
                    })
                    account["pending"] = None
                    log(account, stamp, f"按后续公开报价模拟{'买入' if buy else '卖出'}；含配置费用和滑点", event["id"])
            if account["pending"]:
                continue
        position = account["position"]
        if position:
            quote = quotes.get(position["symbol"])
            if not quote or quote["quote_time"][:10] != stamp[:10]:
                log(account, stamp, "持仓报价缺失，保留上次估值并等待", event["id"])
                continue
            position.update(mark=quote["price"], mark_time=quote["quote_time"])
            account["equity"] = account["cash"] + quote["price"]*position["quantity"]
            account["peak"] = max(account["peak"], account["equity"])
            change = (quote["price"]/position["entry_price"]-1)*100
            drawdown = (1-account["equity"]/account["peak"])*100
            reason = None
            if drawdown >= rules["sim_drawdown_limit_pct"]:
                reason = "组合回撤防线"
            elif change <= -rules["sim_stop_loss_pct"]:
                reason = "模拟价格止损"
            elif change >= rules["sim_take_profit_pct"]:
                reason = "模拟止盈"
            elif latest["market"].get("risk") == "高" or event["stage"] == "退潮回避":
                reason = "市场风险或人工退潮确认"
            elif policy == "research" and latest.get("exit_failed", latest["sector"].get("started") is False) is True:
                reason = "策略条件失效"
            elif policy == "cycle" and (len(event["dates"]) in rules["sim_exit_days"] or len(event["dates"]) > max(rules["sim_exit_days"])):
                reason = "第3或第5个已采集交易日期的减险退出假设"
            if reason:
                account["pending"] = dict(side="sell", symbol=position["symbol"], event_id=event["id"],
                                          signal_time=max(stamp, latest.get("observed_at", stamp), quote["quote_time"]), reason=reason)
                log(account, stamp, f"生成模拟卖单：{reason}；等待后续可卖报价", event["id"])
        elif not account["pending"]:
            account["equity"] = account["cash"]
            if (1-account["equity"]/account["peak"])*100 >= rules["sim_drawdown_limit_pct"]:
                log(account, stamp, "停止新增模拟仓位：组合回撤触线", event["id"])
                continue
            day = len(event["dates"])
            rebound = policy == "cycle" and day == rules["sim_reentry_day"] and event["stage"] == "回补确认"
            leg = event.get("entry_key") or event["id"] + (":rebound" if rebound else ":start")
            market_confirmed = policy == "research" or (
                first["market"].get("new_low") is True and event["stage"] in ("启动观察", "延续观察", "回补确认"))
            if not market_confirmed:
                log(account, stamp, "等待：首次大盘新低数据及人工止跌/回补证据确认。当前数据不足，暂不模拟买入", event["id"])
            elif policy == "cycle" and not 1 <= day <= rules["sim_start_max_days"] and not rebound:
                log(account, stamp, "等待：当前不在启动或已确认回补窗口", event["id"])
            elif leg in account["completed_legs"]:
                log(account, stamp, "已执行本事件该阶段，等待后续阶段", event["id"])
            elif latest["sector"].get("started") and latest["market"].get("risk") != "高":
                leaders = latest.get("leaders")
                if not leaders:
                    log(account, stamp, "等待：板块候选梯队不可用", event["id"])
                    continue
                symbol = leaders[0]["symbol"]
                known_quote = quotes.get(symbol) or {}
                signal_time = max(stamp, latest.get("observed_at", stamp), known_quote.get("quote_time", stamp))
                account["pending"] = dict(side="buy", symbol=symbol, event_id=event["id"], signal_time=signal_time,
                                          reason=event.get("signal_reason") or ("回补确认" if rebound else "启动确认"), leg=leg)
                log(account, stamp, "生成模拟买单，等待下一可得报价；连板涨停可能无法成交", event["id"])
        account["curve"].append({"time": stamp, "equity": account["equity"]})
        account["curve"] = account["curve"][-500:]
    return account


def run_simulation():
    events = list_events()
    with database() as db:
        # 多个采集线程只允许一个读改写账户。
        db.execute("BEGIN IMMEDIATE")
        account = read(db)
        if not account:
            return
        save(db, step(account, events))


@router.get("")
def get_account():
    with database() as db:
        account = read(db)
        reviews = [json.loads(row[0]) for row in db.execute("SELECT payload FROM strategy_reviews ORDER BY trade_date DESC LIMIT 20")]
        return {"account": account, "reviews": reviews}


@router.post("/review-today")
def review_today():
    from app.cycle.engine import load_config
    from app.cycle.market import fetch_daily
    import httpx
    now = datetime.now(TZ)
    today = now.date().isoformat()
    config = load_config()
    window = config["market_new_low_lookback_days"]
    try:
        daily = fetch_daily("sh000001", max(60, window + 10))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(503, "指数日线暂不可用，请稍后重试") from exc
    previous = daily[daily.trade_date < today].tail(window)
    current = daily[daily.trade_date == today]
    if len(previous) < window or current.empty:
        raise HTTPException(422, "当前日期缺少完整的指数日线或前置窗口，暂不生成判断")
    row = current.iloc[-1]
    prior_low, today_low = float(previous.low.min()), float(row.low)
    events = [event for event in list_events() if event["start_date"] == today]
    prior_close, today_close = float(previous.close.min()), float(row.close)
    qualifies = today_low < prior_low or today_close < prior_close
    report = {
        "trade_date": today, "reviewed_at": now.isoformat(), "source": "腾讯上证指数日线",
        "window": window, "previous_low": prior_low,
        "previous_low_date": previous.loc[previous.low.idxmin(), "trade_date"],
        "today_low": today_low, "market_new_low": qualifies,
        "previous_close_low": prior_close, "today_close": today_close,
        "action": "待进一步核验" if qualifies else "不交易",
        "reason": "指数新低前提满足，仍需核验当时分时止跌、回补和后续可成交报价" if qualifies else
            "当日最低价与最新收盘参考值均未低于各自的前置观察窗最低值，未满足本版策略的大盘新低门槛",
        "events": [{"name": event["name"], "first_at": event["first_at"],
                    "initial_pct": event["first"]["sector"].get("pct"),
                    "initial_limit_up": event["first"]["sector"].get("limit_up")} for event in events],
        "mode": "盘后核验" if now.strftime("%H:%M") >= "15:00" else "盘中截至当前核验",
    }
    with database() as db:
        schema(db)
        db.execute("INSERT OR REPLACE INTO strategy_reviews VALUES(?,?)", (today, encode(report)))
    return report


@router.post("/start")
def start():
    from app.cycle.engine import load_config
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        account = read(db)
        if not account:
            account = new_account(load_config())
            log(account, account["created_at"], "模拟账户已启动，等待启动后的新鲜行情。先核对大盘新低、止跌与事件阶段，再生成模拟信号。")
        account["status"] = "running"
        save(db, account)
    return {"account": account}


@router.post("/replay-today")
def replay_today():
    """用户授权的起始日回溯，仅对可确定不满足前提的日期自动落账。"""
    report = review_today()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        account = read(db)
        if not account:
            from app.cycle.engine import load_config
            account = new_account(load_config())
        completed = account.setdefault("replayed_dates", {})
        if report["trade_date"] not in completed:
            account.setdefault("inception_date", report["trade_date"])
            completed[report["trade_date"]] = {
                "reviewed_at": report["reviewed_at"], "action": report["action"],
                "reason": report["reason"], "mode": "用户授权起始日回溯",
            }
            log(account, report["reviewed_at"],
                f"起始日回放 {report['trade_date']}：{report['action']}。{report['reason']}。"
                "符合前提的日期仍需按当时快照和后续报价逐笔复核。")
            save(db, account)
    return {"account": account, "review": report}


@router.post("/pause")
def pause():
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        account = read(db)
        if not account:
            raise HTTPException(404, "尚未启动策略模拟")
        account["status"] = "paused"
        save(db, account)
    return {"account": account}


@router.post("/exit")
def request_exit():
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        account = read(db)
        if not account:
            raise HTTPException(404, "尚未启动策略模拟")
        position = account["position"]
        if position:
            account["pending"] = dict(side="sell", symbol=position["symbol"], event_id=position["event_id"],
                                      signal_time=datetime.now(TZ).isoformat(), reason="人工请求退出模拟持仓")
            account["status"] = "running"
        else:
            account["pending"] = None
        log(account, datetime.now(TZ).isoformat(), "已请求模拟退出或撤销待买订单，等待后续行情及可卖条件")
        save(db, account)
    return {"account": account}
