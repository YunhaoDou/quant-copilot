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


def evaluate_live(symbol):
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
    data = {"as_of":now.isoformat(), "data_timestamp":quote["quote_time"],
        "market":{"env":env,"index_above_key_ma":above},
        "account":{"has_position":False}, "sector":{},
        "stock":{"symbol":normalized[2:],"price":quote["price"],"ma":ma,"ma_slopes":slopes}}
    result = rules.run(data,cfg)
    result["next_action"] = "真实价格与均线已接通；主线、资金与账户证据未齐，禁止据此建仓"
    response = {"result":result,"quote":quote,"moving_averages":ma,"slopes":slopes,
        "source":{"provider":payload["provider"],"quote_time":quote["quote_time"],
        "daily_through":str(daily.trade_date.max()),"index_through":str(index.trade_date.max()),
        "fetched_at":payload["fetched_at"],"adjustment":"不复权"},
        "missing_evidence":["多日板块成交额占比和涨停梯队","调整日承接与趋势中军地位","可核验资金共振","带时间的回踩及次日确认","账户可用现金和已用仓位"],
        "note":"实时公开报价可能延迟；无Mock回退，无自动交易。规则有效性尚未回测证明。"}
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS trend_leader_audit (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        db.execute("INSERT INTO trend_leader_audit VALUES(?,?,?)",(result["audit_log_id"],now.isoformat(),encode({"input":data,"config":cfg,"output":response})))
    return response


@router.get("/{symbol}")
def live(symbol: str):
    try:
        return evaluate_live(symbol)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503,"真实数据核验失败，未生成信号："+str(exc)[:140]) from exc
