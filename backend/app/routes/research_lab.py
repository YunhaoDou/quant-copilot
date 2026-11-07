"""迁移研究工作台接口，不包含券商交易或自动发送消息。"""
from concurrent.futures import ThreadPoolExecutor
import json
import copy
from threading import Lock
from time import monotonic

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import httpx

from app.services import research_lab as lab, research_store as store
from app.config import settings

router = APIRouter(prefix="/research-lab", tags=["综合研究工作台"])
_cache = {}
_cache_lock = Lock()


def run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        # 不把含密钥、代理认证或Webhook的URL放到响应中。
        raise HTTPException(503, "真实数据或模型服务暂不可用（" + type(exc).__name__ + "），请稍后重试；未回退演示数据") from exc


def cached(fn, *args, **kwargs):
    key = json.dumps([fn.__name__, args, kwargs], sort_keys=True)
    ttl = store.config()["cache_ttl"]
    with _cache_lock:
        value = _cache.get(key)
        if value and monotonic() - value[0] < ttl:
            return copy.deepcopy(value[1])
    result = run(fn, *args, **kwargs)
    with _cache_lock:
        if len(_cache) > 100:
            _cache.clear()
        _cache[key] = (monotonic(), copy.deepcopy(result))
    return result


class Diagnosis(BaseModel):
    symbol: str = Field(default="600519", max_length=20)
    count: int = Field(default=252, ge=30, le=640)
    capital: float = Field(default=100000, gt=0, le=1e10)
    risk_budget_pct: float = Field(default=1, gt=0, le=20)
    max_position_pct: float = Field(default=10, gt=0, le=100)


@router.post("/diagnose")
def diagnose(req: Diagnosis):
    data = cached(lab.diagnose, **req.model_dump())
    return dict(data, id=store.save_report(data))


class FundRequest(BaseModel):
    code: str = Field(default="510300", pattern=r"^\d{6}$")
    count: int = Field(default=252, ge=30, le=640)
    warning_high: float = Field(default=1.5, gt=0, le=50)
    danger_high: float = Field(default=3, gt=0, le=100)
    warning_low: float = Field(default=-1.5, ge=-50, lt=0)
    danger_low: float = Field(default=-3, ge=-100, lt=0)


@router.post("/fund")
def fund(req: FundRequest):
    data = cached(lab.fund_deep, **req.model_dump())
    return dict(data, id=store.save_report(data))


@router.get("/fund/{code}/holdings")
def holdings(code: str):
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(422, "基金代码无效")
    return run(lab.fund_holdings, code)


@router.get("/fund/{code}/estimate")
def estimate(code: str):
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(422, "基金代码无效")
    return cached(lab.fund_estimate, code)


@router.get("/rankings")
def rankings(order: str = Query("amount", pattern="^(amount|gainers|losers)$")):
    return cached(lab.rankings, order)


class Comparison(BaseModel):
    codes: list[str] = Field(min_length=2, max_length=3)
    count: int = Field(default=252, ge=30, le=640)


@router.post("/compare")
def compare(req: Comparison):
    if len(set(req.codes)) < 2 or any(not code.isdigit() or len(code) != 6 for code in req.codes):
        raise HTTPException(422, "请输入至少两只不同的六位基金代码")
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda code: cached(lab.fund_deep, code, req.count), list(dict.fromkeys(req.codes))))
    # 各自区间收益单独标日期，不混称同一回测区间。
    return {"rows": rows, "note": "各基金可得历史可能不同，比较时核对起止日期；收益口径见每份报告。"}


class Simulation(BaseModel):
    capital: float = Field(default=100000, gt=0, le=1e10)
    monthly: float = Field(default=5000, ge=0, le=1e8)
    years: int = Field(default=5, ge=1, le=30)
    annual_return: float = Field(default=.06, ge=-.5, le=.5)
    volatility: float = Field(default=.2, ge=0, le=1)
    target: float = Field(default=500000, gt=0, le=1e12)
    simulations: int = Field(default=2000, ge=100, le=5000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)


@router.post("/simulate")
def simulate(req: Simulation):
    data = run(lab.monte_carlo, **req.model_dump())
    return dict(data, id=store.save_report(data))


@router.get("/reports")
def reports(code: str = Query("", max_length=30)):
    return store.reports(code)


@router.get("/reports/{rid}")
def report(rid: int):
    return run(store.report, rid)


@router.delete("/reports/{rid}")
def delete_report(rid: int):
    store.clear(rid)
    return {"ok": True}


@router.delete("/reports")
def clear_reports():
    store.clear()
    return {"ok": True}


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


@router.get("/reports/{rid}/chat")
def chats(rid: int):
    return store.chats(rid)


@router.post("/reports/{rid}/chat")
def chat(rid: int, req: Question):
    return run(store.ask, rid, req.question)


@router.delete("/reports/{rid}/chat")
def clear_chat(rid: int):
    store.clear(rid, chat_only=True)
    return {"ok": True}


@router.get("/config")
def config():
    return store.public_config()


@router.put("/config")
def config_save(req: dict):
    return run(store.save_config, req)


@router.post("/connection-test")
def connection_test():
    return run(store.complete, [{"role": "user", "content": "请只回复：连接成功"}])


@router.get("/reports/{rid}/notification-preview")
def preview(rid: int):
    data = run(store.report, rid)
    return {"text": f"研究快照：{data.get('name','')} {data.get('code','')}\n数据源：{data.get('source','')}\n日期：{data.get('as_of',data.get('fetched_at',''))}\n" + json.dumps(data.get("metrics", data.get("assumptions", {})), ensure_ascii=False) + "\n仅供研究，非买卖指令。"}


class Send(BaseModel):
    channel: str = Field(pattern="^(lark|discord)$")


@router.post("/reports/{rid}/notify")
def notify(rid: int, req: Send):
    cfg = store.config()
    url = cfg["notifications"].get(req.channel) or (settings.LARK_WEBHOOK_URL if req.channel == "lark" else settings.DISCORD_WEBHOOK_URL)
    if not url:
        raise HTTPException(422, "尚未配置该通知渠道")
    message = preview(rid)["text"]
    payload = {"msg_type": "text", "content": {"text": message}} if req.channel == "lark" else {"content": message}
    def send():
        r = httpx.post(url, json=payload, timeout=10)
        r.raise_for_status()
        if req.channel == "lark" and r.json().get("code", r.json().get("StatusCode", 0)) != 0:
            raise ValueError("飞书返回发送失败")
        return {"ok": True}
    return run(send)
