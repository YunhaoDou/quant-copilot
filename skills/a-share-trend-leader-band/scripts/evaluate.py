#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股「趋势+龙头波段」五环闸门 —— 确定性判定脚本。

把「主线定方向 → 龙头定标的 → 买点定时机 → 卖点定生死 → 仓位定存活」
写成一条依序通过的判定流水线：任一环不通过即停止，不跳环、不补数据、不改阈值。
本脚本只做规则判定，不取数、不预测、不下单。

两种取数模式：
    建仓模式（account.has_position = false）：环1 → 环2 → 环3 → 环5。
    持仓模式（account.has_position = true） ：只跑环4。环1/环2 是建仓门槛，
        持仓后不再重复判定；板块退潮通过 sector.breakdown / laggards_collapsed 参与环4。

用法:
    python scripts/evaluate.py --input examples/input.json --config config.json

退出码:
    0  已产出判定结果（decision 为 REJECT/WAIT 也是有效结果）
    2  输入/配置文件读不了、结构不合法的错误契约（stdout 仍输出最小 JSON，见 SKILL.md）

输入契约: references/input-schema.md
判定口径: references/framework.md
禁止清单: references/forbidden.md
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from datetime import datetime
from pathlib import Path

EXIT_OK = 0
EXIT_INPUT = 2

NEXT_ACTION = {
    "BUY_CANDIDATE": "等待人工确认；不得自动下单",
    "WAIT": "继续监控，等待右侧确认",
    "REJECT": "不交易，等待下一候选",
    "EXIT": "人工确认后离场，不得等反弹",
    "REDUCE": "人工确认后减仓/收缩",
    "HOLD": "持有并每日核对卖点",
}

# 两种模式共用的必需字段
BASE_INPUT_PATHS = [
    "as_of",
    "data_timestamp",
    "market.env",
    "market.index_above_key_ma",
    "account.has_position",
]

REQUIRED_CONFIG_PATHS = [
    "data.max_age_hours",
    "mainline.strong_share",
    "mainline.potential_share",
    "mainline.consecutive_expand_days",
    "mainline.limit_up_min",
    "mainline.consecutive_limit_up_days",
    "mainline.require_tier_no_gap",
    "mainline.require_adjustment_resilient",
    "leader.market_cap_min_yi",
    "leader.market_cap_max_yi",
    "leader.avg_turnover_min_yi",
    "leader.avg_turnover_max_yi",
    "leader.turnover_20e8_yi",
    "leader.consecutive_turnover_20e8_days",
    "leader.ma_periods",
    "leader.require_above_ma10_long",
    "leader.require_volume_pattern",
    "leader.require_institutional_resonance",
    "entry.allowed_ma",
    "entry.volume_shrink_ratio_max",
    "entry.require_intraday_recover",
    "entry.require_stabilizing_candle",
    "entry.require_next_day_confirm",
    "entry.forbid_far_from_ma10",
    "exit.ma_exit",
    "exit.require_close_confirm",
    "position.risk_per_trade",
    "position.stop_loss_pct",
    "position.env_caps",
]


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_dt(value) -> datetime:
    """解析带时区偏移的 ISO 8601 时间戳。缺时区视为不可用（否则跨时区比较会错）。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("时间戳必须是非空 ISO 8601 字符串")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("时间戳缺少时区偏移（如 +08:00），无法比较数据新鲜度")
    return dt


def get_path(data, path: str):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def is_num(value) -> bool:
    """有限数值（排除 bool / NaN / Infinity / 超出 float 范围的整数）。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def as_int(value):
    """整数（或纯数字字符串）转 int；bool / 小数 / 其他一律返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        return int(text) if text.isdigit() else None
    return None


def add_reason(reasons: list, code: str, msg: str) -> None:
    reasons.append({"code": code, "msg": msg})


def validate_config(cfg) -> list:
    """配置缺字段/类型错/阈值荒谬时返回问题列表（调用方以退出码 2 处理）。"""
    if not isinstance(cfg, dict):
        return ["config 必须是 JSON 对象"]

    problems = []
    for path in REQUIRED_CONFIG_PATHS:
        if get_path(cfg, path) is None:
            problems.append(f"config 缺少字段：{path}")
    if problems:
        return problems

    def num(path, *, low=None, high=None, low_open=False, high_open=False):
        value = get_path(cfg, path)
        if not is_num(value):
            problems.append(f"{path} 必须是数值")
            return None
        if low is not None and (value < low or (low_open and value == low)):
            problems.append(f"{path} 必须{'大于' if low_open else '不小于'} {low}")
            return None
        if high is not None and (value > high or (high_open and value == high)):
            problems.append(f"{path} 必须{'小于' if high_open else '不大于'} {high}")
            return None
        return float(value)

    def integer(path, min_value=1):
        value = get_path(cfg, path)
        if not is_num(value) or not float(value).is_integer():
            problems.append(f"{path} 必须是整数")
            return None
        value = int(value)
        if value < min_value:
            problems.append(f"{path} 必须 ≥ {min_value}")
            return None
        return value

    def boolean(path):
        if not isinstance(get_path(cfg, path), bool):
            problems.append(f"{path} 必须是 true/false")

    num("data.max_age_hours", low=0, low_open=True)
    strong_share = num("mainline.strong_share", low=0, high=1, low_open=True)
    potential_share = num("mainline.potential_share", low=0, high=1, low_open=True)
    if (
        strong_share is not None
        and potential_share is not None
        and potential_share > strong_share
    ):
        problems.append("mainline.potential_share 不能大于 mainline.strong_share")
    integer("mainline.consecutive_expand_days", min_value=2)
    integer("mainline.limit_up_min")
    integer("mainline.consecutive_limit_up_days", min_value=2)
    boolean("mainline.require_tier_no_gap")
    boolean("mainline.require_adjustment_resilient")

    market_cap_min = num("leader.market_cap_min_yi", low=0, low_open=True)
    market_cap_max = num("leader.market_cap_max_yi", low=0, low_open=True)
    if (
        market_cap_min is not None
        and market_cap_max is not None
        and market_cap_min > market_cap_max
    ):
        problems.append("leader.market_cap_max_yi 不能小于 leader.market_cap_min_yi")
    turnover_min = num("leader.avg_turnover_min_yi", low=0, low_open=True)
    turnover_max = num("leader.avg_turnover_max_yi", low=0, low_open=True)
    if (
        turnover_min is not None
        and turnover_max is not None
        and turnover_min > turnover_max
    ):
        problems.append(
            "leader.avg_turnover_max_yi 不能小于 leader.avg_turnover_min_yi"
        )
    num("leader.turnover_20e8_yi", low=0, low_open=True)
    integer("leader.consecutive_turnover_20e8_days", min_value=2)

    periods = get_path(cfg, "leader.ma_periods")
    if not isinstance(periods, list) or len(periods) < 2:
        problems.append("leader.ma_periods 必须是至少 2 个周期的数组")
    else:
        parsed_periods = []
        for item in periods:
            if not is_num(item) or not float(item).is_integer() or item <= 0:
                problems.append("leader.ma_periods 必须是正整数数组")
                break
            parsed_periods.append(int(item))
        else:
            if any(
                parsed_periods[i] >= parsed_periods[i + 1]
                for i in range(len(parsed_periods) - 1)
            ):
                problems.append("leader.ma_periods 必须严格递增（如 [5,10,21,55]）")
    boolean("leader.require_above_ma10_long")
    boolean("leader.require_volume_pattern")
    boolean("leader.require_institutional_resonance")

    allowed_ma = get_path(cfg, "entry.allowed_ma")
    if not isinstance(allowed_ma, list) or not allowed_ma:
        problems.append("entry.allowed_ma 必须是非空数组")
    else:
        for item in allowed_ma:
            if not is_num(item) or not float(item).is_integer() or item <= 0:
                problems.append("entry.allowed_ma 必须是正整数数组")
                break
    num("entry.volume_shrink_ratio_max", low=0, high=1, low_open=True)
    boolean("entry.require_intraday_recover")
    boolean("entry.require_stabilizing_candle")
    boolean("entry.require_next_day_confirm")
    boolean("entry.forbid_far_from_ma10")
    integer("exit.ma_exit")
    boolean("exit.require_close_confirm")

    num("position.risk_per_trade", low=0, high=1, low_open=True)
    num("position.stop_loss_pct", low=0, high=1, low_open=True, high_open=True)
    env_caps = get_path(cfg, "position.env_caps")
    if not isinstance(env_caps, dict) or not env_caps:
        problems.append("position.env_caps 必须是非空对象")
    else:
        for env, caps in env_caps.items():
            if not isinstance(caps, dict):
                problems.append(f"position.env_caps.{env} 必须是对象")
                continue
            total = caps.get("total")
            single = caps.get("single")
            if not is_num(total) or not (0 < total <= 1):
                problems.append(f"position.env_caps.{env}.total 必须在 (0,1] 内")
                continue
            if not is_num(single) or not (0 < single <= total):
                problems.append(f"position.env_caps.{env}.single 必须在 (0,total] 内")
    if get_path(cfg, "exit.ma_exit") != 20:
        problems.append("exit.ma_exit 当前只支持20，与输入close_below_ma20一致")
    return problems


# --------------------------------------------------------------------------- #
# 输出构造
# --------------------------------------------------------------------------- #
def build_output(
    inp,
    cfg,
    *,
    as_of,
    stage: str,
    decision: str,
    mainline: str = "NOT_EVALUATED",
    leader: str = "NOT_EVALUATED",
    entry: str = "NOT_EVALUATED",
    exit_signal: str = "NOT_EVALUATED",
    cap: float = 0.0,
    reasons=None,
    missing_fields=None,
    freshness: str = "UNKNOWN",
    age_hours=None,
) -> dict:
    """所有分支都走这里，保证输出字段齐整——Agent 不需要为失败分支写特例。"""
    stock = inp.get("stock") if isinstance(inp, dict) else None
    stock = stock if isinstance(stock, dict) else {}
    sector = inp.get("sector") if isinstance(inp, dict) else None
    sector = sector if isinstance(sector, dict) else {}

    price = stock.get("price")
    stop_pct = cfg["position"]["stop_loss_pct"]
    held = get_path(inp, "account.has_position") is True
    fixed = get_path(inp, "account.stop_loss_price")
    stop_loss_price = (fixed if is_num(fixed) and fixed > 0 else None) if held else (
        round(price * (1 - stop_pct), 3) if is_num(price) and price > 0 else None
    )
    risk_amount_pct = round(cap * stop_pct * 100, 2)
    symbol = stock.get("symbol") if isinstance(stock.get("symbol"), str) else None
    sector_name = sector.get("name") if isinstance(sector.get("name"), str) else None

    return {
        "timestamp": as_of.isoformat() if as_of else None,
        "symbol": symbol,
        "sector": sector_name,
        "stage": stage,
        "decision": decision,
        "mainline_status": mainline,
        "leader_status": leader,
        "entry_signal": entry,
        "exit_signal": exit_signal,
        "position_cap_pct": round(cap * 100, 2),
        "stop_loss_price": stop_loss_price,
        "risk_amount_pct": risk_amount_pct,
        "market_env": get_path(inp, "market.env"),
        "index_above_key_ma": get_path(inp, "market.index_above_key_ma"),
        "data_freshness": freshness,
        "data_age_hours": round(age_hours, 2) if age_hours is not None else None,
        "missing_fields": missing_fields or [],
        "reasons": reasons if reasons is not None else [],
        "human_confirm_required": True,
        "next_action": NEXT_ACTION.get(decision, "人工复核"),
        "audit_log_id": str(uuid.uuid4()),
    }


# --------------------------------------------------------------------------- #
# 输入形状校验（单位/类型写错属于数据错误，不是「不通过」）
# --------------------------------------------------------------------------- #
def validate_shapes(inp, cfg, has_position: bool) -> list:
    errors = []

    def expect_bool(path):
        value = get_path(inp, path)
        if value is not None and not isinstance(value, bool):
            errors.append((path, "必须是 true/false"))

    expect_bool("market.index_above_key_ma")
    expect_bool("account.has_position")

    env = get_path(inp, "market.env")
    if not isinstance(env, str):
        errors.append(("market.env", "必须是字符串（bull/range/bear）"))

    if has_position:
        _validate_position_mode_shapes(inp, errors)
    else:
        _validate_entry_mode_shapes(inp, cfg, errors)
    return errors


def _validate_position_mode_shapes(inp, errors) -> None:
    """持仓模式：只需 exit 数据可用；sector 可选，仅识别退潮信号。"""
    if not isinstance(get_path(inp, "stock.symbol"), str):
        errors.append(("stock.symbol", "必须是字符串"))

    exit_data = get_path(inp, "stock.exit")
    if exit_data is not None and not isinstance(exit_data, dict):
        errors.append(("stock.exit", "必须是对象"))
    elif isinstance(exit_data, dict):
        for key in ("close_below_ma20", "high_volume_stall", "intraday_below_ma20"):
            value = exit_data.get(key)
            if value is not None and not isinstance(value, bool):
                errors.append((f"stock.exit.{key}", "必须是 true/false"))

    sector = get_path(inp, "sector")
    if sector is not None and not isinstance(sector, dict):
        errors.append(("sector", "必须是对象"))
    elif isinstance(sector, dict):
        for key in ("breakdown", "laggards_collapsed"):
            value = sector.get(key)
            if value is not None and not isinstance(value, bool):
                errors.append((f"sector.{key}", "必须是 true/false"))

    price = get_path(inp, "stock.price")
    if price is not None and (not is_num(price) or price <= 0):
        errors.append(("stock.price", "必须是大于 0 的数值"))


def _validate_entry_mode_shapes(inp, cfg, errors) -> None:
    def expect_num(path, *, positive=False):
        value = get_path(inp, path)
        if not is_num(value):
            errors.append((path, "必须是数值"))
        elif positive and value <= 0:
            errors.append((path, "必须大于 0"))

    def expect_bool(path):
        value = get_path(inp, path)
        if value is not None and not isinstance(value, bool):
            errors.append((path, "必须是 true/false"))

    for path in ("stock.symbol",):
        if not isinstance(get_path(inp, path), str):
            errors.append((path, "必须是字符串"))
    for path in (
        "stock.is_mainline_mid_cap",
        "stock.above_ma10_long",
        "stock.volume_pattern_ok",
        "stock.institutional_resonance",
        "sector.has_tier_no_gap",
        "sector.adjustment_resilient",
        "sector.breakdown",
        "sector.laggards_collapsed",
    ):
        expect_bool(path)

    expect_num("stock.price", positive=True)
    expect_num("stock.market_cap_yi", positive=True)
    for path in ("stock.avg_turnover_yi",):
        value = get_path(inp, path)
        if value is not None and (not is_num(value) or value <= 0):
            errors.append((path, "必须是大于 0 的数值"))
    turnover_history = get_path(inp, "stock.turnover_history_yi")
    if turnover_history is not None:
        if not isinstance(turnover_history, list) or not all(
            is_num(x) and x >= 0 for x in turnover_history
        ):
            errors.append(("stock.turnover_history_yi", "必须是非负数值数组"))

    shares = get_path(inp, "sector.amount_share_history")
    if not isinstance(shares, list) or not shares:
        errors.append(("sector.amount_share_history", "必须是非空数组"))
    elif not all(is_num(x) for x in shares):
        errors.append(("sector.amount_share_history", "每个元素必须是有限数值"))
    elif any(x < 0 or x > 1 for x in shares):
        errors.append(
            (
                "sector.amount_share_history",
                "必须是 0–1 的占比小数（8% 写 0.08，不是 8）",
            )
        )

    counts = get_path(inp, "sector.limit_up_counts")
    if not isinstance(counts, list) or not counts:
        errors.append(("sector.limit_up_counts", "必须是非空数组"))
    elif not all(is_num(x) and float(x).is_integer() and x >= 0 for x in counts):
        errors.append(("sector.limit_up_counts", "每个元素必须是非负整数"))

    ma = get_path(inp, "stock.ma")
    if not isinstance(ma, dict):
        errors.append(("stock.ma", "必须是对象"))
    else:
        for period in cfg["leader"]["ma_periods"]:
            value = ma.get(str(period))
            if not is_num(value) or value <= 0:
                errors.append((f"stock.ma.{period}", "必须是大于 0 的数值"))

    entry = get_path(inp, "stock.entry")
    if entry is not None and not isinstance(entry, dict):
        errors.append(("stock.entry", "必须是对象"))
    elif isinstance(entry, dict):
        ratio = entry.get("volume_shrink_ratio")
        if ratio is not None and (not is_num(ratio) or not (0 < ratio <= 1)):
            errors.append(
                (
                    "stock.entry.volume_shrink_ratio",
                    "必须是 (0,1] 的小数（缩量到均量一半写 0.5，不要写 50）",
                )
            )
        for key in (
            "far_from_ma10",
            "intraday_break_recovered",
            "stabilizing_candle",
            "next_day_confirm",
        ):
            value = entry.get(key)
            if value is not None and not isinstance(value, bool):
                errors.append((f"stock.entry.{key}", "必须是 true/false"))
        pullback = entry.get("pullback_to_ma")
        if pullback is not None and as_int(pullback) is None:
            errors.append(
                ("stock.entry.pullback_to_ma", "必须是整数均线周期（5/10/20）")
            )

    # 建仓模式不消费 stock.exit，因此不校验它（只校验当前模式实际用到的数据块）


# --------------------------------------------------------------------------- #
# 五环判定
# --------------------------------------------------------------------------- #
def check_mainline(sector, cfg, reasons) -> str:
    """环1：主线定方向。返回 PASS / WATCH / REJECT。"""
    mainline_cfg = cfg["mainline"]
    hist = [float(x) for x in (sector.get("amount_share_history") or [])]
    counts = [int(x) for x in (sector.get("limit_up_counts") or [])]
    if not hist:
        add_reason(reasons, "MAINLINE_NO_SHARE", "缺少板块成交额占比历史")
        return "REJECT"
    last_share = hist[-1]

    days = mainline_cfg["consecutive_expand_days"]
    if len(hist) < days:
        expanding = False
        add_reason(
            reasons,
            "MAINLINE_HISTORY_SHORT",
            f"成交额占比历史仅 {len(hist)} 日，判断连续放大需要 ≥{days} 日",
        )
    else:
        window = hist[-days:]
        expanding = all(window[i] > window[i - 1] for i in range(1, len(window)))

    need_days = mainline_cfg["consecutive_limit_up_days"]
    if len(counts) < need_days:
        limit_ok = False
        add_reason(
            reasons,
            "MAINLINE_LIMIT_HISTORY_SHORT",
            f"涨停家数历史仅 {len(counts)} 日，判断连续性需要 ≥{need_days} 日",
        )
    else:
        limit_ok = all(c >= mainline_cfg["limit_up_min"] for c in counts[-need_days:])

    tier_ok = (
        (sector.get("has_tier_no_gap") is True)
        if mainline_cfg["require_tier_no_gap"]
        else True
    )
    adjust_ok = (
        (sector.get("adjustment_resilient") is True)
        if mainline_cfg["require_adjustment_resilient"]
        else True
    )

    if (
        last_share >= mainline_cfg["strong_share"]
        and expanding
        and limit_ok
        and tier_ok
        and adjust_ok
    ):
        return "PASS"

    if last_share >= mainline_cfg["potential_share"]:
        if not expanding:
            add_reason(
                reasons, "MAINLINE_NOT_EXPANDING", "成交额占比未连续放大（脉冲式）"
            )
        if not limit_ok:
            add_reason(
                reasons,
                "MAINLINE_LIMIT_UP_WEAK",
                f"涨停家数未连续 {need_days} 日 ≥{mainline_cfg['limit_up_min']} 家",
            )
        if not tier_ok:
            add_reason(reasons, "MAINLINE_TIER_GAP", "板块梯队断层，无接力高度")
        if not adjust_ok:
            add_reason(reasons, "MAINLINE_ADJUST_WEAK", "调整日不抗跌/未验证")
        return "WATCH"

    add_reason(
        reasons,
        "MAINLINE_SHARE_LOW",
        f"成交额占比 {last_share:.2%} 低于潜在主线底线 {mainline_cfg['potential_share']:.0%}",
    )
    return "REJECT"


def check_leader(stock, cfg, reasons) -> str:
    """环2：龙头定标的。返回 PASS / REJECT（收集全部不满足项，不只报第一条）。"""
    leader_cfg = cfg["leader"]
    ok = True

    if stock.get("is_mainline_mid_cap") is not True:
        add_reason(
            reasons, "LEADER_NOT_MID_CAP", "非第一主线内的趋势中军（情绪先锋不算）"
        )
        ok = False

    market_cap = stock.get("market_cap_yi")
    if not is_num(market_cap) or not (
        leader_cfg["market_cap_min_yi"] <= market_cap <= leader_cfg["market_cap_max_yi"]
    ):
        add_reason(
            reasons,
            "LEADER_MARKET_CAP",
            f"市值 {market_cap} 不在 {leader_cfg['market_cap_min_yi']}—"
            f"{leader_cfg['market_cap_max_yi']} 亿区间",
        )
        ok = False

    avg_turnover = stock.get("avg_turnover_yi")
    hist = [float(x) for x in (stock.get("turnover_history_yi") or []) if is_num(x)]
    need_days = leader_cfg["consecutive_turnover_20e8_days"]
    liquidity_ok = is_num(avg_turnover) and (
        leader_cfg["avg_turnover_min_yi"]
        <= avg_turnover
        <= leader_cfg["avg_turnover_max_yi"]
    )
    if not liquidity_ok:
        liquidity_ok = len(hist) >= need_days and all(
            v >= leader_cfg["turnover_20e8_yi"] for v in hist[-need_days:]
        )
    if not liquidity_ok:
        add_reason(
            reasons,
            "LEADER_LIQUIDITY",
            f"日均成交额 {avg_turnover} 亿不达标，且无连续 {need_days} 日 "
            f"≥{leader_cfg['turnover_20e8_yi']} 亿记录",
        )
        ok = False

    ma = stock.get("ma") or {}
    values = []
    ma_available = True
    for period in leader_cfg["ma_periods"]:
        value = ma.get(str(period))
        if not is_num(value):
            ma_available = False
            break
        values.append(float(value))
    if not ma_available:
        add_reason(reasons, "LEADER_MA_MISSING", "均线数据不完整，无法判断多头排列")
        ok = False
    else:
        ma_bull = all(values[i] > values[i + 1] for i in range(len(values) - 1))
        if not ma_bull:
            periods = "/".join(str(p) for p in leader_cfg["ma_periods"])
            add_reason(reasons, "LEADER_MA", f"均线非多头排列（需 {periods} 逐级递减）")
            ok = False

    if (
        leader_cfg["require_above_ma10_long"]
        and stock.get("above_ma10_long") is not True
    ):
        add_reason(reasons, "LEADER_ABOVE_MA10", "未长期运行在 10 日线上方")
        ok = False

    if (
        leader_cfg["require_volume_pattern"]
        and stock.get("volume_pattern_ok") is not True
    ):
        add_reason(reasons, "LEADER_VOLUME", "量价结构不满足上涨放量/回调缩量")
        ok = False

    if (
        leader_cfg["require_institutional_resonance"]
        and stock.get("institutional_resonance") is not True
    ):
        add_reason(reasons, "LEADER_RESONANCE", "机构/北向/游资未共振")
        ok = False

    return "PASS" if ok else "REJECT"


def check_entry(stock, cfg, reasons) -> str:
    """环3：买点定时机。返回 CONFIRMED / WAIT / REJECT。

    缺失或类型不对的买点字段一律 WAIT（等待数据/修正），绝不 fail-open。
    """
    entry_cfg = cfg["entry"]
    entry = stock.get("entry")
    if not isinstance(entry, dict):
        add_reason(reasons, "ENTRY_NO_DATA", "缺少 entry 买点数据，无法判断时机")
        return "WAIT"

    required_fields = ["pullback_to_ma", "volume_shrink_ratio"]
    if entry_cfg["forbid_far_from_ma10"]:
        required_fields.append("far_from_ma10")
    if entry_cfg["require_intraday_recover"]:
        required_fields.append("intraday_break_recovered")
    if entry_cfg["require_stabilizing_candle"]:
        required_fields.append("stabilizing_candle")
    if entry_cfg["require_next_day_confirm"]:
        required_fields.append("next_day_confirm")

    missing = [key for key in required_fields if entry.get(key) is None]
    if missing:
        add_reason(reasons, "ENTRY_NO_DATA", f"缺少买点字段：{', '.join(missing)}")
        return "WAIT"

    for key in required_fields:
        if key in ("pullback_to_ma", "volume_shrink_ratio"):
            continue
        if not isinstance(entry[key], bool):
            add_reason(reasons, "ENTRY_INVALID", f"{key} 必须是 true/false")
            return "WAIT"

    if entry_cfg["forbid_far_from_ma10"] and entry["far_from_ma10"] is True:
        add_reason(reasons, "ENTRY_FAR_FROM_MA10", "股价显著远离 10 日线，禁止追高")
        return "REJECT"

    pullback = as_int(entry["pullback_to_ma"])
    allowed = [int(x) for x in entry_cfg["allowed_ma"]]
    if pullback is None or pullback not in allowed:
        add_reason(
            reasons,
            "ENTRY_NO_PULLBACK",
            f"未回踩 {'/'.join(str(a) for a in allowed)} 日线（当前 {entry['pullback_to_ma']}）",
        )
        return "WAIT"

    if (
        entry_cfg["require_intraday_recover"]
        and entry["intraday_break_recovered"] is not True
    ):
        add_reason(reasons, "ENTRY_NOT_RECOVERED", "盘中破线未收回")
        return "WAIT"

    ratio = entry["volume_shrink_ratio"]
    if not is_num(ratio) or not (0 < ratio <= 1):
        add_reason(
            reasons,
            "ENTRY_INVALID",
            "volume_shrink_ratio 必须是 (0,1] 的小数（缩量一半写 0.5）",
        )
        return "WAIT"
    if ratio > entry_cfg["volume_shrink_ratio_max"]:
        add_reason(
            reasons,
            "ENTRY_NOT_SHRINK",
            f"缩量不足：{ratio:.2f} > {entry_cfg['volume_shrink_ratio_max']}",
        )
        return "WAIT"

    if (
        entry_cfg["require_stabilizing_candle"]
        and entry["stabilizing_candle"] is not True
    ):
        add_reason(reasons, "ENTRY_NO_STABILIZING_CANDLE", "未出现止跌 K 线")
        return "WAIT"

    if entry_cfg["require_next_day_confirm"] and entry["next_day_confirm"] is not True:
        add_reason(reasons, "ENTRY_NO_NEXT_DAY_CONFIRM", "次日未翻红/反包确认")
        return "WAIT"

    return "CONFIRMED"


def check_exit(stock, sector, cfg, reasons) -> str:
    """环4：卖点定生死。返回 EXIT / REDUCE / HOLD（信号全部记录，优先级 EXIT > REDUCE）。"""
    exit_cfg = cfg["exit"]
    exit_data = stock.get("exit")
    exit_data = exit_data if isinstance(exit_data, dict) else {}
    signals = []

    if exit_data.get("close_below_ma20") is True:
        add_reason(
            reasons,
            "EXIT_BELOW_MA20",
            f"收盘有效跌破 {exit_cfg['ma_exit']} 日线，无条件离场",
        )
        signals.append("EXIT")
    elif exit_data.get("intraday_below_ma20") is True:
        if exit_cfg["require_close_confirm"]:
            add_reason(
                reasons,
                "EXIT_PENDING_CLOSE",
                f"盘中跌破 {exit_cfg['ma_exit']} 日线但收盘未确认，尾盘再核对，暂不触发卖点",
            )
        else:
            add_reason(
                reasons,
                "EXIT_INTRADAY_BREAK",
                f"配置不要求收盘确认，盘中跌破 {exit_cfg['ma_exit']} 日线即触发卖点",
            )
            signals.append("EXIT")

    if exit_data.get("high_volume_stall") is True:
        add_reason(reasons, "EXIT_HIGH_VOLUME_STALL", "高位放量滞涨，减仓")
        signals.append("REDUCE")

    if sector.get("breakdown") is True:
        add_reason(
            reasons, "EXIT_SECTOR_BREAKDOWN", "板块梯队瓦解/退潮，停止加仓并收缩"
        )
        signals.append("REDUCE")
    if sector.get("laggards_collapsed") is True:
        add_reason(reasons, "EXIT_LAGGARDS_COLLAPSED", "后排批量掉队，板块退潮前兆")
        signals.append("REDUCE")

    if "EXIT" in signals:
        return "EXIT"
    if "REDUCE" in signals:
        return "REDUCE"
    return "HOLD"


def calc_position_cap(env: str, cfg, reasons) -> float:
    """环5：环境上限与单笔风控上限取小。返回占总资金比例（0–1）。"""
    position_cfg = cfg["position"]
    caps = (position_cfg["env_caps"] or {}).get(env)
    if not isinstance(caps, dict):
        add_reason(reasons, "POSITION_ENV_UNKNOWN", f"未知市场环境：{env}")
        return 0.0
    risk_cap = position_cfg["risk_per_trade"] / position_cfg["stop_loss_pct"]
    return round(min(float(caps["single"]), float(caps["total"]), risk_cap), 4)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def required_input_paths(inp, cfg) -> list:
    """按模式给出必需字段：持仓只判环4，不再要求建仓门槛所需的板块/龙头数据。"""
    has_position = get_path(inp, "account.has_position") is True
    if has_position:
        return BASE_INPUT_PATHS + ["stock.symbol"]

    paths = BASE_INPUT_PATHS + [
        "sector.amount_share_history",
        "sector.limit_up_counts",
        "stock.symbol",
        "stock.price",
        "stock.is_mainline_mid_cap",
        "stock.market_cap_yi",
    ]
    paths += [f"stock.ma.{period}" for period in cfg["leader"]["ma_periods"]]
    if cfg["mainline"]["require_tier_no_gap"]:
        paths.append("sector.has_tier_no_gap")
    if cfg["mainline"]["require_adjustment_resilient"]:
        paths.append("sector.adjustment_resilient")
    if cfg["leader"]["require_above_ma10_long"]:
        paths.append("stock.above_ma10_long")
    if cfg["leader"]["require_volume_pattern"]:
        paths.append("stock.volume_pattern_ok")
    if cfg["leader"]["require_institutional_resonance"]:
        paths.append("stock.institutional_resonance")
    return paths


def run(inp, cfg) -> dict:
    """对一份输入跑完整五环，返回输出字典。任何分支都返回完整输出契约。"""
    reasons = []

    if not isinstance(inp, dict):
        add_reason(reasons, "INPUT_NOT_OBJECT", "输入必须是 JSON 对象")
        return build_output(
            {},
            cfg,
            as_of=None,
            stage="数据校验",
            decision="REJECT",
            reasons=reasons,
            freshness="INVALID",
        )

    # --- 必需字段（含 as_of，缺失统一报 DATA_MISSING） ------------------- #
    missing = [
        path for path in required_input_paths(inp, cfg) if get_path(inp, path) is None
    ]
    if missing:
        for path in missing:
            add_reason(reasons, "DATA_MISSING", f"缺少必需字段：{path}")
        return build_output(
            inp,
            cfg,
            as_of=None,
            stage="数据校验",
            decision="REJECT",
            reasons=reasons,
            missing_fields=missing,
        )

    # --- 时点与数据新鲜度 ------------------------------------------------ #
    try:
        as_of = parse_dt(inp.get("as_of"))
    except Exception as exc:  # noqa: BLE001 - 任何解析失败都归为数据不可用
        add_reason(reasons, "AS_OF_INVALID", f"as_of 无法解析：{exc}")
        return build_output(
            inp,
            cfg,
            as_of=None,
            stage="数据校验",
            decision="REJECT",
            reasons=reasons,
            freshness="INVALID",
        )

    try:
        data_ts = parse_dt(inp["data_timestamp"])
    except Exception as exc:  # noqa: BLE001
        add_reason(reasons, "DATA_TIMESTAMP_INVALID", f"data_timestamp 无法解析：{exc}")
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="数据校验",
            decision="REJECT",
            reasons=reasons,
            freshness="INVALID",
        )

    age_hours = (as_of - data_ts).total_seconds() / 3600.0
    if age_hours < 0:
        add_reason(
            reasons,
            "DATA_TIMESTAMP_FUTURE",
            f"data_timestamp 晚于 as_of {abs(age_hours):.1f} 小时，时间戳可疑",
        )
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="数据校验",
            decision="REJECT",
            reasons=reasons,
            freshness="FUTURE",
            age_hours=age_hours,
        )
    if age_hours > cfg["data"]["max_age_hours"]:
        add_reason(
            reasons,
            "DATA_STALE",
            f"数据过期：{age_hours:.1f}h > {cfg['data']['max_age_hours']}h，需重新取数",
        )
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="数据校验",
            decision="REJECT",
            reasons=reasons,
            freshness="STALE",
            age_hours=age_hours,
        )
    freshness = "OK"

    env = get_path(inp, "market.env")
    if not isinstance(env, str) or env not in cfg["position"]["env_caps"]:
        add_reason(
            reasons, "POSITION_ENV_UNKNOWN", f"未知市场环境：{env!r}，无法确定仓位上限"
        )
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="数据校验",
            decision="REJECT",
            reasons=reasons,
            freshness=freshness,
            age_hours=age_hours,
        )

    has_position = get_path(inp, "account.has_position") is True
    shape_errors = validate_shapes(inp, cfg, has_position)
    if shape_errors:
        for path, message in shape_errors:
            add_reason(reasons, "DATA_TYPE_INVALID", f"{path}：{message}")
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="数据校验",
            decision="REJECT",
            reasons=reasons,
            freshness=freshness,
            age_hours=age_hours,
        )

    stock = inp.get("stock") or {}
    stock = stock if isinstance(stock, dict) else {}
    account = inp.get("account") or {}
    account = account if isinstance(account, dict) else {}
    sector = inp.get("sector")
    sector = sector if isinstance(sector, dict) else {}

    # --- 持仓模式：只判环4（环1/环2 是建仓门槛，持仓后不重复判定） ------ #
    if account.get("has_position") is True:
        fixed = account.get("stop_loss_price")
        if fixed is not None and (not is_num(fixed) or fixed <= 0):
            add_reason(reasons, "STOP_INVALID", "固定止损价无效")
            return build_output(inp, cfg, as_of=as_of, stage="数据校验", decision="REJECT", reasons=reasons)
        if is_num(fixed) and is_num(stock.get("price")) and stock["price"] <= fixed:
            add_reason(reasons, "FIXED_STOP_HIT", "触发建仓时保存的固定止损；实际成交仍受T+1及跌停约束")
            return build_output(inp, cfg, as_of=as_of, stage="环4-卖点定生死", decision="EXIT", reasons=reasons)
        exit_data = stock.get("exit")
        if not isinstance(exit_data, dict) or not isinstance(
            exit_data.get("close_below_ma20"), bool
        ):
            # 持仓中却拿不到可核对的卖点数据，不能给「HOLD」这种安抚性结论
            add_reason(
                reasons,
                "EXIT_NO_DATA",
                "持仓中但 exit 数据缺失或不完整（需要布尔字段 close_below_ma20），"
                "无法核对 20 日线；补齐后重跑，未核对前不得加仓",
            )
            return build_output(
                inp,
                cfg,
                as_of=as_of,
                stage="环4-卖点定生死",
                decision="WAIT",
                mainline="NOT_APPLICABLE",
                leader="NOT_APPLICABLE",
                entry="NOT_APPLICABLE",
                exit_signal="NO_DATA",
                cap=0.0,
                reasons=reasons,
                freshness=freshness,
                age_hours=age_hours,
            )

        exit_signal = check_exit(stock, sector, cfg, reasons)
        if exit_signal == "EXIT":
            return build_output(
                inp,
                cfg,
                as_of=as_of,
                stage="环4-卖点定生死",
                decision="EXIT",
                mainline="NOT_APPLICABLE",
                leader="NOT_APPLICABLE",
                entry="NOT_APPLICABLE",
                exit_signal=exit_signal,
                cap=0.0,
                reasons=reasons,
                freshness=freshness,
                age_hours=age_hours,
            )

        cap = calc_position_cap(env, cfg, reasons)
        if env == "bull" and inp["market"]["index_above_key_ma"] is not True:
            add_reason(
                reasons,
                "ENV_INDEX_CONFLICT",
                "环境声明为 bull，但指数不在关键均线上方：数据冲突视为不通过，仓位上限归零",
            )
            cap = 0.0
        decision = "REDUCE" if exit_signal == "REDUCE" else "HOLD"
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="环4-卖点定生死",
            decision=decision,
            mainline="NOT_APPLICABLE",
            leader="NOT_APPLICABLE",
            entry="NOT_APPLICABLE",
            exit_signal=exit_signal,
            cap=cap,
            reasons=reasons,
            freshness=freshness,
            age_hours=age_hours,
        )

    # 已确认的退潮优先否决建仓。
    if not has_position and (sector.get("breakdown") is True or sector.get("laggards_collapsed") is True):
        add_reason(reasons, "SECTOR_BREAKDOWN", "板块退潮，禁止新增仓位")
        return build_output(inp, cfg, as_of=as_of, stage="环1-主线定方向", decision="REJECT", reasons=reasons)

    # --- 建仓模式：环1 → 环2 → 环3 → 环5 -------------------------------- #
    mainline = check_mainline(sector, cfg, reasons)
    if mainline != "PASS":
        decision = "WAIT" if mainline == "WATCH" else "REJECT"
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="环1-主线定方向",
            decision=decision,
            mainline=mainline,
            reasons=reasons,
            freshness=freshness,
            age_hours=age_hours,
        )

    leader = check_leader(stock, cfg, reasons)
    if leader != "PASS":
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="环2-龙头定标的",
            decision="REJECT",
            mainline=mainline,
            leader=leader,
            reasons=reasons,
            freshness=freshness,
            age_hours=age_hours,
        )

    entry_signal = check_entry(stock, cfg, reasons)
    if entry_signal != "CONFIRMED":
        decision = "REJECT" if entry_signal == "REJECT" else "WAIT"
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="环3-买点定时机",
            decision=decision,
            mainline=mainline,
            leader=leader,
            entry=entry_signal,
            exit_signal="NOT_APPLICABLE",
            reasons=reasons,
            freshness=freshness,
            age_hours=age_hours,
        )

    slopes = stock.get("ma_slopes") or {}
    if any(not is_num(slopes.get(str(n))) or slopes[str(n)] <= 0 for n in cfg["leader"]["ma_periods"]):
        add_reason(reasons, "MA_SLOPE_UNCONFIRMED", "需各周期均线斜率为正的证据")
        return build_output(inp, cfg, as_of=as_of, stage="环2-龙头定标的", decision="WAIT", reasons=reasons)

    # --- 环5：仓位定存活；顺带校验环境数据是否自相矛盾 ------------------ #
    cap = calc_position_cap(env, cfg, reasons)
    if env == "bull" and inp["market"]["index_above_key_ma"] is not True:
        add_reason(
            reasons,
            "ENV_INDEX_CONFLICT",
            "环境声明为 bull，但指数不在关键均线上方：数据冲突视为不通过，先确认环境",
        )
        return build_output(
            inp,
            cfg,
            as_of=as_of,
            stage="环5-仓位定存活",
            decision="WAIT",
            mainline=mainline,
            leader=leader,
            entry=entry_signal,
            exit_signal="NOT_APPLICABLE",
            cap=0.0,
            reasons=reasons,
            freshness=freshness,
            age_hours=age_hours,
        )

    invested, cash = account.get("invested_pct"), account.get("cash_pct")
    if not all(is_num(v) and 0 <= v <= 1 for v in (invested, cash)) or invested + cash > 1.000001:
        add_reason(reasons, "ACCOUNT_BUDGET_MISSING", "需提供0至1之间的已用总仓位与可用现金比例，且合计不得超过1")
        return build_output(inp, cfg, as_of=as_of, stage="环5-仓位定存活", decision="WAIT", reasons=reasons)
    cap = min(cap, max(0, cfg["position"]["env_caps"][env]["total"]-invested), cash)
    if cap <= 0:
        add_reason(reasons, "ACCOUNT_BUDGET_EXHAUSTED", "可用现金或环境总仓预算已耗尽")
        return build_output(inp, cfg, as_of=as_of, stage="环5-仓位定存活", decision="WAIT", reasons=reasons)
    return build_output(
        inp,
        cfg,
        as_of=as_of,
        stage="环5-仓位定存活",
        decision="BUY_CANDIDATE",
        mainline=mainline,
        leader=leader,
        entry=entry_signal,
        exit_signal="NOT_APPLICABLE",
        cap=cap,
        reasons=reasons,
        freshness=freshness,
        age_hours=age_hours,
    )


def _error_contract(stage: str, code: str, msg: str) -> dict:
    """退出码 2 的最小错误契约（不是完整判定输出）。"""
    return {
        "stage": stage,
        "decision": "REJECT",
        "reasons": [{"code": code, "msg": msg}],
        "human_confirm_required": True,
        "next_action": "修正问题后重跑；未产出判定结果前不得交易",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="A股「趋势+龙头波段」五环闸门确定性判定（只做规则判定，不下单）"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="输入 JSON 路径，契约见 references/input-schema.md",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="阈值配置路径，默认使用脚本上一级目录的 config.json",
    )
    args = parser.parse_args(argv)

    config_path = args.config or str(
        Path(__file__).resolve().parents[1] / "config.json"
    )
    try:
        cfg = load_json(config_path)
        inp = load_json(args.input)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                _error_contract("配置加载", "INPUT_UNREADABLE", str(exc)),
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_INPUT

    try:
        problems = validate_config(cfg)
    except Exception as exc:  # noqa: BLE001 - 配置校验自身异常也要走错误契约
        print(
            json.dumps(
                _error_contract(
                    "配置校验", "INTERNAL_ERROR", f"{type(exc).__name__}: {exc}"
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_INPUT
    if problems:
        payload = _error_contract("配置校验", "CONFIG_INVALID", "; ".join(problems))
        payload["reasons"] = [
            {"code": "CONFIG_INVALID", "msg": problem} for problem in problems
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_INPUT

    try:
        result = run(inp, cfg)
        payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    except Exception as exc:  # noqa: BLE001 - 宁可给错误契约，也不要 traceback
        print(
            json.dumps(
                _error_contract(
                    "内部错误", "INTERNAL_ERROR", f"{type(exc).__name__}: {exc}"
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_INPUT

    print(payload)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
