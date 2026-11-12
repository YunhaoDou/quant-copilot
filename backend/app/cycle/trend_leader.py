"""趋势中军规则与真实行情适配；缺失证据保持未知，不生成订单。"""
import importlib.util
import json
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.cycle.market import fetch_daily, fetch_quotes, normalize_symbol
from app.cycle.live import TZ
from app.cycle.events import database, encode

router = APIRouter(prefix="/trend-leader", tags=["趋势中军波段"])
BASE = Path(__file__).resolve().parents[3] / "skills/a-share-trend-leader-band"
spec = importlib.util.spec_from_file_location("trend_leader_rules", BASE / "scripts/evaluate.py")
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


def evaluate_live(symbol, account=None):
    normalized = normalize_symbol(symbol)
    if not normalized[2:].startswith(("0", "3", "6", "8", "4", "92")):
        raise ValueError("请输入A股公司证券代码")
    now = datetime.now(TZ)
    payload = fetch_quotes([symbol])
    if not payload["quotes"]:
        raise ValueError("供应商未返回真实报价")
    quote = payload["quotes"][0]
    # 全部均线统一使用不复权日线，避免与现价、固定止损混用价格基准。
    daily = fetch_daily(symbol, 120, adjust="")
    index = fetch_daily("510300", 120, adjust="")
    daily = daily.sort_values("trade_date")
    index = index.sort_values("trade_date")
    if len(daily) < 61 or len(index) < 61:
        raise ValueError("真实历史不足61个交易日")
    closes = daily.close.astype(float)
    idx = index.close.astype(float)
    periods = (5,10,21,55)
    ma = {str(n): float(closes.tail(n).mean()) for n in periods}
    slopes = {str(n): float(closes.tail(n).mean()-closes.iloc[:-1].tail(n).mean()) for n in periods}
    above = float(idx.iloc[-1]) > float(idx.tail(20).mean())
    env = "bull" if above and idx.tail(20).mean() > idx.tail(60).mean() else "range" if above else "bear"
    cfg = json.loads((BASE / "config.json").read_text())
    now = datetime.now(TZ)
    position = (account or {}).get("position") or {}
    held = position.get("symbol") == normalized[2:]
    equity = (account or {}).get("equity",0)
    budget = {"has_position":held}
    if equity > 0:
        budget.update(invested_pct=min(1,position.get("quantity",0)*quote["price"]/equity) if position else 0,
            cash_pct=min(1,(account or {}).get("cash",0)/equity),
            stop_loss_price=position.get("stop_loss_price"))
        # 估值在新报价下变化，比例以同一时点资产重新归一。
        mark_equity = (account or {}).get("cash",0)+position.get("quantity",0)*quote["price"]
        if mark_equity > 0:
            budget["cash_pct"] = (account or {}).get("cash",0)/mark_equity
            budget["invested_pct"] = 1-budget["cash_pct"]
    data = {"as_of":now.isoformat(), "data_timestamp":quote["quote_time"],
        "market":{"env":env,"index_above_key_ma":above},
        "account":budget, "sector":{},
        "stock":{"symbol":normalized[2:],"price":quote["price"],"ma":ma,"ma_slopes":slopes}}
    if held:
        data["stock"]["exit"] = {"close_below_ma20":float(closes.iloc[-1]) < float(closes.tail(20).mean())}
    result = rules.run(data,cfg)
    if not held and result["decision"] != "BUY_CANDIDATE":
        result["next_action"] = "真实价格与均线已接通；主线及资金证据未齐，禁止据此建仓"
    response = {"result":result,"quote":quote,"moving_averages":ma,"slopes":slopes,
        "source":{"provider":payload["provider"],"quote_time":quote["quote_time"],
        "daily_through":str(daily.trade_date.max()),"index_through":str(index.trade_date.max()),
        "evaluated_at":now.isoformat(),"fetched_at":payload["fetched_at"],"adjustment":"不复权"},
        "missing_evidence":(["板块退潮证据（不影响独立固定止损及均线退出）"] if held else
            ["多日板块成交额占比和涨停梯队","调整日承接与趋势中军地位","可核验资金共振","带时间的回踩及次日确认"]+([] if account else ["账户可用现金和已用仓位"])),
        "note":"实时公开报价可能延迟；无Mock回退，无自动交易。规则有效性尚未回测证明。"}
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS trend_leader_audit (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        db.execute("INSERT INTO trend_leader_audit VALUES(?,?,?)",(result["audit_log_id"],now.isoformat(),encode({"input":data,"config":cfg,"output":response})))
    return response


@router.get("/{symbol}")
def live(symbol: str):
    try:
        from app.cycle.trend_forward import track
        result = evaluate_live(symbol)
        track(symbol)
        return result
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503,"真实数据核验失败，未生成信号："+str(exc)[:140]) from exc
