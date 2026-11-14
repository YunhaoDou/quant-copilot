"""综合研究档案和私有模型配置；本地SQLite不进入版本控制。"""
from datetime import datetime
from pathlib import Path
import copy
import json
import sqlite3
from contextlib import closing

import httpx

from app.config import settings
from app.cycle.live import TZ

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "research-lab.sqlite"
DEFAULTS = {"active_provider": "deepseek", "model": "", "cache_ttl": 120, "history_max": 100, "proxy": "",
    "alerts": {"warning_high": 1.5, "danger_high": 3, "warning_low": -1.5, "danger_low": -3},
    "providers": {"deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat", "api_key": ""},
        "openai": {"base_url": "https://api.openai.com/v1", "model": "", "api_key": ""},
        "anthropic": {"base_url": "https://api.anthropic.com/v1", "model": "", "api_key": ""},
        "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "", "api_key": ""}},
    "notifications": {"lark": "", "discord": ""}}


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY,payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,code TEXT,name TEXT,created_at TEXT,payload TEXT,legacy_key TEXT UNIQUE); CREATE TABLE IF NOT EXISTS chats (report_id INTEGER,role TEXT,content TEXT,created_at TEXT);")
    DB_PATH.chmod(0o600)
    return c


def config():
    with closing(connect()) as c, c:
        row = c.execute("SELECT payload FROM config WHERE id=1").fetchone()
    result = copy.deepcopy(DEFAULTS)
    if row:
        saved = json.loads(row[0])
        result.update({k:v for k,v in saved.items() if k not in ("providers", "notifications")})
        for key, value in saved.get("providers", {}).items():
            if key in result["providers"]:
                result["providers"][key].update(value)
        result["notifications"].update(saved.get("notifications", {}))
    return result


def secret_for(pid, cfg):
    return cfg["providers"][pid].get("api_key") or {"deepseek": settings.DEEPSEEK_API_KEY, "openai": settings.OPENAI_API_KEY, "anthropic": settings.ANTHROPIC_API_KEY}.get(pid, "")


def public_config():
    cfg = config()
    for pid, values in cfg["providers"].items():
        secret = secret_for(pid, cfg)
        values.pop("api_key", None)
        values["key_set"] = bool(secret)
        values["key_masked"] = "****" + secret[-4:] if secret else ""
    cfg["notifications"] = {key: bool(value or getattr(settings, "LARK_WEBHOOK_URL" if key == "lark" else "DISCORD_WEBHOOK_URL")) for key, value in cfg["notifications"].items()}
    cfg["proxy_set"] = bool(cfg.pop("proxy", ""))
    return cfg


def save_config(changes):
    cfg = config()
    for key in ("active_provider", "model", "cache_ttl", "history_max", "proxy", "alerts"):
        if key in changes:
            cfg[key] = changes[key]
    for pid, values in changes.get("providers", {}).items():
        if pid not in cfg["providers"]:
            raise ValueError("未知模型供应商")
        for key in ("base_url", "model", "api_key"):
            if key in values and (key != "api_key" or values[key]):
                cfg["providers"][pid][key] = values[key]
    for channel, url in changes.get("notifications", {}).items():
        if channel not in ("lark", "discord"):
            raise ValueError("未知通知渠道")
        if url:
            cfg["notifications"][channel] = url
    if cfg["active_provider"] not in cfg["providers"]:
        raise ValueError("未知模型供应商")
    for values in cfg["providers"].values():
        url = httpx.URL(values["base_url"])
        if url.scheme not in ("http", "https") or not url.host or url.userinfo:
            raise ValueError("模型地址必须是无凭据的HTTP(S)地址")
    cfg["cache_ttl"] = max(0, min(3600, int(cfg["cache_ttl"])))
    cfg["history_max"] = max(1, min(1000, int(cfg["history_max"])))
    with closing(connect()) as c, c:
        c.execute("INSERT OR REPLACE INTO config VALUES (1,?)", (json.dumps(cfg),))
    return public_config()


def save_report(payload, legacy_key=None):
    with closing(connect()) as c, c:
        cursor = c.execute("INSERT OR IGNORE INTO reports (kind,code,name,created_at,payload,legacy_key) VALUES (?,?,?,?,?,?)", (payload["kind"], payload.get("code", ""), payload.get("name", ""), datetime.now(TZ).isoformat(), json.dumps(payload, ensure_ascii=False, allow_nan=False), legacy_key))
        if not cursor.rowcount:
            return c.execute("SELECT id FROM reports WHERE legacy_key=?", (legacy_key,)).fetchone()[0]
        return cursor.lastrowid


def reports(code=""):
    with closing(connect()) as c, c:
        return [dict(r) for r in c.execute("SELECT id,kind,code,name,created_at FROM reports WHERE code LIKE ? ORDER BY id DESC LIMIT ?", ("%" + code + "%", config()["history_max"]))]


def report(rid):
    with closing(connect()) as c, c:
        row = c.execute("SELECT payload FROM reports WHERE id=?", (rid,)).fetchone()
        if not row:
            raise ValueError("档案不存在")
        return dict(json.loads(row[0]), id=rid)


def chats(rid):
    with closing(connect()) as c, c:
        return [dict(r) for r in c.execute("SELECT role,content,created_at FROM chats WHERE report_id=? ORDER BY rowid", (rid,))]


def clear(rid=None, chat_only=False):
    with closing(connect()) as c, c:
        c.execute("DELETE FROM chats" + (" WHERE report_id=?" if rid is not None else ""), (rid,) if rid is not None else ())
        if not chat_only:
            c.execute("DELETE FROM reports" + (" WHERE id=?" if rid is not None else ""), (rid,) if rid is not None else ())


def complete(messages, cfg=None):
    cfg = cfg or config()
    pid = cfg["active_provider"]
    provider = cfg["providers"][pid]
    key = secret_for(pid, cfg)
    model = cfg.get("model") or provider.get("model") or (settings.DEEPSEEK_MODEL if pid == "deepseek" else "")
    if not key or not model:
        raise ValueError("请先配置所选供应商的密钥与模型名称；未生成虚构AI报告")
    base = provider["base_url"].rstrip("/")
    with httpx.Client(trust_env=False, proxy=cfg.get("proxy") or None, timeout=90) as client:
        if pid == "anthropic":
            response = client.post(base + "/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, json={"model": model, "max_tokens": 1600, "messages": messages})
        else:
            response = client.post(base + "/chat/completions", headers={"Authorization": "Bearer " + key}, json={"model": model, "max_tokens": 1600, "messages": messages})
        response.raise_for_status()
        data = response.json()
    text = "".join(b.get("text", "") for b in data.get("content", [])) if pid == "anthropic" else data["choices"][0]["message"]["content"]
    if not text:
        raise ValueError("模型未返回正文")
    return {"content": text, "provider": pid, "model": model, "generated_at": datetime.now(TZ).isoformat(), "note": "模型观点，非已核验事实或买卖指令"}


def ask(rid, question):
    payload = report(rid)
    # 不将完整长日线重复发给模型；只发送已获取的事实、日期与用户对话。
    context = {k:v for k,v in payload.items() if k not in ("chart", "path", "premium_history", "id")}
    prompt = "你是中文投资研究助手。只引用所给事实，明确数据日期、假设与缺项，不预测必涨，不承诺收益，不自动交易。\n" + json.dumps(context, ensure_ascii=False)[:22000]
    history = [{"role": r["role"], "content": r["content"]} for r in chats(rid)[-12:]]
    answer = complete([{"role": "user", "content": prompt}, {"role": "assistant", "content": "我将区分事实与假设。"}, *history, {"role": "user", "content": question}])
    with closing(connect()) as c, c:
        for role, content in (("user", question), ("assistant", answer["content"])):
            c.execute("INSERT INTO chats VALUES (?,?,?,?)", (rid, role, content, datetime.now(TZ).isoformat()))
    return answer
