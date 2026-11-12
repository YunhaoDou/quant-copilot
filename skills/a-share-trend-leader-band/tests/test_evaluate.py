# -*- coding: utf-8 -*-
"""五环闸门判定脚本的回归测试。

运行:
    python -m pytest skills/a-share-trend-leader-band/tests -q

覆盖点：五环每一环的 PASS/WATCH/REJECT 分支、建仓/持仓两种模式、数据新鲜度与单位陷阱、
fail-closed 数据缺口、输出契约、配置校验（类型/范围/顺序）、阈值来自 config.json、CLI 退出码。
"""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / "scripts" / "evaluate.py"

spec = importlib.util.spec_from_file_location("evaluate", SCRIPT)
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)

CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
EXAMPLE = json.loads((BASE / "examples" / "input.json").read_text(encoding="utf-8"))

CONTRACT_KEYS = {
    "timestamp",
    "symbol",
    "sector",
    "stage",
    "decision",
    "mainline_status",
    "leader_status",
    "entry_signal",
    "exit_signal",
    "position_cap_pct",
    "stop_loss_price",
    "risk_amount_pct",
    "market_env",
    "index_above_key_ma",
    "data_freshness",
    "data_age_hours",
    "missing_fields",
    "reasons",
    "human_confirm_required",
    "next_action",
    "audit_log_id",
}


def run(inp=None, cfg=None):
    return evaluate.run(copy.deepcopy(EXAMPLE if inp is None else inp), cfg or CFG)


def reason_codes(result):
    return {item["code"] for item in result["reasons"]}


def with_patch(**patches):
    """按 'a.b.c' 路径深拷贝一份示例输入并打补丁（None 表示删除该键）。"""
    inp = copy.deepcopy(EXAMPLE)
    for path, value in patches.items():
        parts = path.split(".")
        node = inp
        for part in parts[:-1]:
            node = node[part]
        if value is None:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = value
    return inp


def held_minimal(**patches):
    """持仓模式最小输入：只需要行情环境 + exit，不再要求板块/龙头数据。"""
    inp = {
        "as_of": EXAMPLE["as_of"],
        "data_timestamp": EXAMPLE["data_timestamp"],
        "market": {"env": "range", "index_above_key_ma": True},
        "stock": {"symbol": "000000", "exit": {"close_below_ma20": False}},
        "account": {"has_position": True},
    }
    for path, value in patches.items():
        parts = path.split(".")
        node = inp
        for part in parts[:-1]:
            node = node[part]
        if value is None:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = value
    return inp


# --------------------------------------------------------------------------- #
# 基线 & 输出契约
# --------------------------------------------------------------------------- #
def test_config_self_check_passes():
    assert evaluate.validate_config(copy.deepcopy(CFG)) == []


def test_example_passes_all_five_rings():
    result = run()
    assert result["decision"] == "BUY_CANDIDATE"
    assert result["stage"] == "环5-仓位定存活"
    assert result["mainline_status"] == "PASS"
    assert result["leader_status"] == "PASS"
    assert result["entry_signal"] == "CONFIRMED"
    # bull 单票上限 33%，小于 2%/5% 反推的 40%，取 33%
    assert result["position_cap_pct"] == 33.0
    # 止损价 = 11.8 * (1 - 5%)，风险金额 = 33% * 5%
    assert result["stop_loss_price"] == 11.21
    assert result["risk_amount_pct"] == 1.65
    assert result["human_confirm_required"] is True
    assert "不得自动下单" in result["next_action"]
    assert result["data_freshness"] == "OK"


@pytest.mark.parametrize(
    "input_case",
    [
        with_patch(),
        with_patch(**{"data_timestamp": "2026-11-01T15:00:00+08:00"}),
        with_patch(**{"sector.amount_share_history": None}),
        with_patch(**{"stock.entry.far_from_ma10": True}),
        with_patch(
            **{"account.has_position": True, "stock.exit.close_below_ma20": True}
        ),
        held_minimal(),
        held_minimal(**{"stock.exit": None}),
    ],
)
def test_every_branch_returns_full_contract(input_case):
    result = run(input_case)
    assert CONTRACT_KEYS <= set(result)
    assert result["decision"] in {
        "BUY_CANDIDATE",
        "WAIT",
        "REJECT",
        "EXIT",
        "REDUCE",
        "HOLD",
    }
    assert result["human_confirm_required"] is True


def test_decision_is_stable_but_audit_id_is_not():
    first, second = run(), run()
    assert first["decision"] == second["decision"]
    assert first["audit_log_id"] != second["audit_log_id"]


def test_non_object_input_rejected_without_crash():
    result = evaluate.run([], CFG)
    assert result["decision"] == "REJECT"
    assert "INPUT_NOT_OBJECT" in reason_codes(result)


# --------------------------------------------------------------------------- #
# 数据校验
# --------------------------------------------------------------------------- #
def test_stale_data_is_rejected():
    result = run(with_patch(data_timestamp="2026-11-10T09:00:00+08:00"))
    assert result["decision"] == "REJECT"
    assert result["data_freshness"] == "STALE"
    assert "DATA_STALE" in reason_codes(result)


def test_data_age_exactly_max_is_still_fresh():
    # as_of 15:30，前一天 15:30 = 恰好 24h，未超过 max_age_hours，不算过期
    result = run(with_patch(data_timestamp="2026-11-10T15:30:00+08:00"))
    assert result["decision"] == "BUY_CANDIDATE"
    assert result["data_age_hours"] == 24.0
    assert result["data_freshness"] == "OK"


def test_future_data_is_rejected():
    result = run(with_patch(data_timestamp="2026-11-12T15:00:00+08:00"))
    assert result["decision"] == "REJECT"
    assert result["data_freshness"] == "FUTURE"
    assert "DATA_TIMESTAMP_FUTURE" in reason_codes(result)


def test_naive_as_of_is_rejected():
    result = run(with_patch(as_of="2026-11-11T15:30:00"))
    assert result["decision"] == "REJECT"
    assert "AS_OF_INVALID" in reason_codes(result)
    assert result["data_freshness"] == "INVALID"


def test_naive_data_timestamp_is_rejected():
    result = run(with_patch(data_timestamp="2026-11-11T15:00:00"))
    assert result["decision"] == "REJECT"
    assert "DATA_TIMESTAMP_INVALID" in reason_codes(result)


def test_missing_as_of_is_reported_as_missing_field():
    result = run(with_patch(as_of=None))
    assert result["decision"] == "REJECT"
    assert result["stage"] == "数据校验"
    assert "as_of" in result["missing_fields"]
    assert "DATA_MISSING" in reason_codes(result)


def test_missing_required_field_is_listed():
    result = run(with_patch(**{"sector.has_tier_no_gap": None}))
    assert result["decision"] == "REJECT"
    assert result["stage"] == "数据校验"
    assert "sector.has_tier_no_gap" in result["missing_fields"]
    assert "DATA_MISSING" in reason_codes(result)


def test_percent_scale_mistake_is_rejected():
    result = run(with_patch(**{"sector.amount_share_history": [4, 6, 9]}))
    assert result["decision"] == "REJECT"
    assert "DATA_TYPE_INVALID" in reason_codes(result)
    assert any("0.08" in item["msg"] for item in result["reasons"])


def test_nan_share_is_rejected():
    result = run(
        with_patch(**{"sector.amount_share_history": [0.04, "nan_placeholder", 0.09]})
    )
    assert result["decision"] == "REJECT"
    assert "DATA_TYPE_INVALID" in reason_codes(result)


def test_unknown_market_env_is_rejected():
    result = run(with_patch(**{"market.env": "sideways"}))
    assert result["decision"] == "REJECT"
    assert "POSITION_ENV_UNKNOWN" in reason_codes(result)


def test_unhashable_market_env_does_not_crash():
    result = run(with_patch(**{"market.env": ["bull"]}))
    assert result["decision"] == "REJECT"
    assert "POSITION_ENV_UNKNOWN" in reason_codes(result)


# --------------------------------------------------------------------------- #
# 环1 主线
# --------------------------------------------------------------------------- #
def test_mainline_watch_when_share_below_strong_threshold():
    result = run(with_patch(**{"sector.amount_share_history": [0.05, 0.06, 0.07]}))
    assert result["decision"] == "WAIT"
    assert result["stage"] == "环1-主线定方向"
    assert result["mainline_status"] == "WATCH"


def test_mainline_share_exactly_at_strong_threshold_passes():
    result = run(with_patch(**{"sector.amount_share_history": [0.04, 0.06, 0.08]}))
    assert result["decision"] == "BUY_CANDIDATE"
    assert result["mainline_status"] == "PASS"


def test_mainline_share_exactly_at_potential_threshold_is_watch():
    result = run(with_patch(**{"sector.amount_share_history": [0.03, 0.04, 0.05]}))
    assert result["mainline_status"] == "WATCH"


def test_mainline_reject_when_share_below_potential():
    result = run(with_patch(**{"sector.amount_share_history": [0.02, 0.03, 0.04]}))
    assert result["decision"] == "REJECT"
    assert result["mainline_status"] == "REJECT"
    assert "MAINLINE_SHARE_LOW" in reason_codes(result)


def test_mainline_reject_on_pulse_share():
    result = run(with_patch(**{"sector.amount_share_history": [0.06, 0.09, 0.06]}))
    assert result["mainline_status"] == "WATCH"  # 占比仍 ≥5%，但未连续放大
    assert "MAINLINE_NOT_EXPANDING" in reason_codes(result)


def test_mainline_reject_when_limit_up_not_consecutive():
    result = run(with_patch(**{"sector.limit_up_counts": [7, 1]}))
    assert result["mainline_status"] == "WATCH"
    assert "MAINLINE_LIMIT_UP_WEAK" in reason_codes(result)


def test_mainline_limit_up_exactly_five_passes():
    result = run(with_patch(**{"sector.limit_up_counts": [5, 5]}))
    assert result["mainline_status"] == "PASS"


def test_mainline_reject_on_tier_gap():
    result = run(with_patch(**{"sector.has_tier_no_gap": False}))
    assert result["mainline_status"] == "WATCH"
    assert "MAINLINE_TIER_GAP" in reason_codes(result)


def test_mainline_reject_on_weak_adjustment_day():
    result = run(with_patch(**{"sector.adjustment_resilient": False}))
    assert result["mainline_status"] == "WATCH"
    assert "MAINLINE_ADJUST_WEAK" in reason_codes(result)


def test_mainline_short_history_cannot_confirm_expansion():
    result = run(with_patch(**{"sector.amount_share_history": [0.09]}))
    assert result["decision"] == "WAIT"
    assert "MAINLINE_HISTORY_SHORT" in reason_codes(result)


# --------------------------------------------------------------------------- #
# 环2 龙头
# --------------------------------------------------------------------------- #
def test_leader_market_cap_boundaries_are_inclusive():
    for cap in (150, 1000):
        result = run(with_patch(**{"stock.market_cap_yi": cap}))
        assert result["leader_status"] == "PASS", cap


def test_leader_reject_on_market_cap():
    result = run(with_patch(**{"stock.market_cap_yi": 80}))
    assert result["decision"] == "REJECT"
    assert result["stage"] == "环2-龙头定标的"
    assert "LEADER_MARKET_CAP" in reason_codes(result)


def test_leader_reject_on_broken_ma_order():
    result = run(
        with_patch(**{"stock.ma": {"5": 10.0, "10": 11.5, "21": 11.0, "55": 10.0}})
    )
    assert result["decision"] == "REJECT"
    assert "LEADER_MA" in reason_codes(result)


def test_leader_reject_on_poor_liquidity():
    result = run(
        with_patch(
            **{"stock.avg_turnover_yi": 5, "stock.turnover_history_yi": [5, 5, 5]}
        )
    )
    assert result["decision"] == "REJECT"
    assert "LEADER_LIQUIDITY" in reason_codes(result)


def test_leader_liquidity_fallback_without_avg_turnover():
    result = run(with_patch(**{"stock.avg_turnover_yi": None}))
    assert result["leader_status"] == "PASS"


def test_leader_reject_without_institutional_resonance():
    result = run(with_patch(**{"stock.institutional_resonance": False}))
    assert result["decision"] == "REJECT"
    assert "LEADER_RESONANCE" in reason_codes(result)


def test_leader_collects_all_failures_not_just_first():
    result = run(
        with_patch(
            **{
                "stock.market_cap_yi": 80,
                "stock.institutional_resonance": False,
                "stock.volume_pattern_ok": False,
            }
        )
    )
    assert {"LEADER_MARKET_CAP", "LEADER_RESONANCE", "LEADER_VOLUME"} <= reason_codes(
        result
    )


# --------------------------------------------------------------------------- #
# 环3 买点（必须 fail-closed）
# --------------------------------------------------------------------------- #
def test_entry_reject_when_far_from_ma10():
    result = run(with_patch(**{"stock.entry.far_from_ma10": True}))
    assert result["decision"] == "REJECT"
    assert result["stage"] == "环3-买点定时机"
    assert "ENTRY_FAR_FROM_MA10" in reason_codes(result)


def test_entry_wait_when_far_from_ma10_missing():
    # 回归：缺字段曾经直接放行成 BUY_CANDIDATE
    result = run(with_patch(**{"stock.entry.far_from_ma10": None}))
    assert result["decision"] == "WAIT"
    assert "ENTRY_NO_DATA" in reason_codes(result)


def test_entry_invalid_type_is_rejected():
    result = run(with_patch(**{"stock.entry.far_from_ma10": "true"}))
    assert result["decision"] == "REJECT"
    assert "DATA_TYPE_INVALID" in reason_codes(result)


def test_entry_wait_when_required_entry_field_missing():
    result = run(with_patch(**{"stock.entry.volume_shrink_ratio": None}))
    assert result["decision"] == "WAIT"
    assert "ENTRY_NO_DATA" in reason_codes(result)


def test_entry_wait_without_next_day_confirm():
    result = run(with_patch(**{"stock.entry.next_day_confirm": False}))
    assert result["decision"] == "WAIT"
    assert "ENTRY_NO_NEXT_DAY_CONFIRM" in reason_codes(result)


def test_entry_wait_when_volume_not_shrunk():
    result = run(with_patch(**{"stock.entry.volume_shrink_ratio": 0.8}))
    assert result["decision"] == "WAIT"
    assert "ENTRY_NOT_SHRINK" in reason_codes(result)


def test_entry_volume_shrink_exactly_half_is_accepted():
    result = run(with_patch(**{"stock.entry.volume_shrink_ratio": 0.5}))
    assert result["entry_signal"] == "CONFIRMED"


def test_entry_volume_shrink_percent_or_negative_is_rejected():
    for bad in (40, -0.2, 0):
        result = run(with_patch(**{"stock.entry.volume_shrink_ratio": bad}))
        assert result["decision"] == "REJECT", bad
        assert "DATA_TYPE_INVALID" in reason_codes(result), bad


def test_entry_pullback_must_be_integer_period():
    for bad in (10.9, "ten", True):
        result = run(with_patch(**{"stock.entry.pullback_to_ma": bad}))
        assert result["decision"] == "REJECT", bad
        assert "DATA_TYPE_INVALID" in reason_codes(result), bad


def test_entry_wait_when_no_entry_data():
    result = run(with_patch(**{"stock.entry": None}))
    assert result["decision"] == "WAIT"
    assert "ENTRY_NO_DATA" in reason_codes(result)


# --------------------------------------------------------------------------- #
# 环4 卖点（持仓模式只判环4）
# --------------------------------------------------------------------------- #
def test_position_exit_on_close_below_ma20():
    result = run(
        with_patch(
            **{"account.has_position": True, "stock.exit.close_below_ma20": True}
        )
    )
    assert result["decision"] == "EXIT"
    assert result["stage"] == "环4-卖点定生死"
    assert result["position_cap_pct"] == 0.0
    assert "离场" in result["next_action"]


def test_position_exit_surfaces_even_if_entry_gates_would_fail():
    # 持仓中跌破 20 日线，即使板块/龙头数据已经不符合建仓门槛，也必须给出 EXIT
    result = run(
        with_patch(
            **{
                "account.has_position": True,
                "stock.exit.close_below_ma20": True,
                "sector.amount_share_history": [0.02, 0.02, 0.02],
                "stock.market_cap_yi": 80,
            }
        )
    )
    assert result["decision"] == "EXIT"
    assert result["mainline_status"] == "NOT_APPLICABLE"
    assert result["leader_status"] == "NOT_APPLICABLE"


def test_position_does_not_get_rejected_by_entry_gates():
    result = run(
        with_patch(**{"account.has_position": True, "stock.market_cap_yi": 80})
    )
    assert result["decision"] == "HOLD"


def test_minimal_held_position_input_works():
    result = run(held_minimal())
    assert result["decision"] == "HOLD"
    assert result["mainline_status"] == "NOT_APPLICABLE"
    assert result["entry_signal"] == "NOT_APPLICABLE"


def test_held_position_incomplete_exit_data_never_reassures():
    # 回归：exit={} 曾经返回 HOLD + 33% 仓位 + 空理由（fail-open）
    for exit_payload in ({}, {"high_volume_stall": True}, {"close_below_ma20": None}):
        result = run(held_minimal(**{"stock.exit": exit_payload}))
        assert result["decision"] == "WAIT", exit_payload
        assert result["exit_signal"] == "NO_DATA"
        assert result["position_cap_pct"] == 0.0
        assert "EXIT_NO_DATA" in reason_codes(result)


def test_held_position_without_exit_block_never_reassures():
    result = run(held_minimal(**{"stock.exit": None}))
    assert result["decision"] == "WAIT"
    assert "EXIT_NO_DATA" in reason_codes(result)


def test_position_reduce_on_high_volume_stall():
    result = run(
        with_patch(
            **{
                "market.env": "range",
                "account.has_position": True,
                "stock.exit.high_volume_stall": True,
            }
        )
    )
    assert result["decision"] == "REDUCE"
    assert result["exit_signal"] == "REDUCE"
    assert result["position_cap_pct"] == 25.0


def test_position_reduce_when_sector_breaks_down():
    result = run(
        with_patch(
            **{
                "account.has_position": True,
                "sector.breakdown": True,
            }
        )
    )
    assert result["decision"] == "REDUCE"
    assert "EXIT_SECTOR_BREAKDOWN" in reason_codes(result)


def test_position_reduce_when_laggards_collapse():
    result = run(
        with_patch(
            **{
                "account.has_position": True,
                "sector.laggards_collapsed": True,
            }
        )
    )
    assert result["decision"] == "REDUCE"
    assert "EXIT_LAGGARDS_COLLAPSED" in reason_codes(result)


def test_exit_priority_beats_reduce():
    result = run(
        held_minimal(
            **{
                "stock.exit": {
                    "close_below_ma20": True,
                    "high_volume_stall": True,
                },
                "sector": {"breakdown": True},
            }
        )
    )
    assert result["decision"] == "EXIT"
    assert {"EXIT_BELOW_MA20", "EXIT_HIGH_VOLUME_STALL", "EXIT_SECTOR_BREAKDOWN"} <= (
        reason_codes(result)
    )


def test_position_hold_when_no_sell_signal():
    result = run(with_patch(**{"account.has_position": True}))
    assert result["decision"] == "HOLD"
    assert result["stage"] == "环4-卖点定生死"
    assert result["position_cap_pct"] == 33.0


def test_intraday_break_does_not_trigger_exit_before_close():
    result = run(
        with_patch(
            **{
                "account.has_position": True,
                "stock.exit.intraday_below_ma20": True,
            }
        )
    )
    assert result["decision"] == "HOLD"
    assert "EXIT_PENDING_CLOSE" in reason_codes(result)


def test_intraday_break_triggers_exit_when_close_confirm_disabled():
    strict_cfg = copy.deepcopy(CFG)
    strict_cfg["exit"]["require_close_confirm"] = False
    result = run(
        held_minimal(**{"stock.exit.intraday_below_ma20": True}), cfg=strict_cfg
    )
    assert result["decision"] == "EXIT"
    assert "EXIT_INTRADAY_BREAK" in reason_codes(result)


def test_held_position_env_conflict_zeroes_cap():
    result = run(
        held_minimal(**{"market": {"env": "bull", "index_above_key_ma": False}})
    )
    assert result["decision"] == "HOLD"
    assert result["position_cap_pct"] == 0.0
    assert "ENV_INDEX_CONFLICT" in reason_codes(result)


# --------------------------------------------------------------------------- #
# 环5 仓位 & 环境冲突
# --------------------------------------------------------------------------- #
def test_bear_environment_caps_position():
    result = run(
        with_patch(**{"market.env": "bear", "market.index_above_key_ma": False})
    )
    assert result["decision"] == "BUY_CANDIDATE"
    assert result["position_cap_pct"] == 10.0
    assert result["risk_amount_pct"] == 0.5


def test_bull_env_conflicting_with_index_gate_waits():
    result = run(with_patch(**{"market.index_above_key_ma": False}))
    assert result["decision"] == "WAIT"
    assert result["stage"] == "环5-仓位定存活"
    assert "ENV_INDEX_CONFLICT" in reason_codes(result)


# --------------------------------------------------------------------------- #
# 阈值必须来自 config.json，且配置本身要被校验
# --------------------------------------------------------------------------- #
def test_thresholds_come_from_config():
    strict_cfg = copy.deepcopy(CFG)
    strict_cfg["mainline"]["strong_share"] = 0.2
    strict_cfg["mainline"]["potential_share"] = 0.15
    result = run(cfg=strict_cfg)
    assert result["decision"] == "REJECT"
    assert result["mainline_status"] == "REJECT"

    loose_cfg = copy.deepcopy(CFG)
    loose_cfg["position"]["env_caps"]["bull"]["single"] = 0.1
    result = run(cfg=loose_cfg)
    assert result["position_cap_pct"] == 10.0


def _bad_config(**patches):
    cfg = copy.deepcopy(CFG)
    for path, value in patches.items():
        parts = path.split(".")
        node = cfg
        for part in parts[:-1]:
            node = node[part]
        if value is None:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = value
    return cfg


@pytest.mark.parametrize(
    "cfg, fragment",
    [
        (_bad_config(**{"leader.avg_turnover_min_yi": None}), "avg_turnover_min_yi"),
        (
            _bad_config(**{"leader.consecutive_turnover_20e8_days": None}),
            "consecutive_turnover",
        ),
        (_bad_config(**{"mainline.strong_share": "0.08"}), "strong_share"),
        (_bad_config(**{"leader.ma_periods": [55, 21, 10, 5]}), "严格递增"),
        (_bad_config(**{"leader.ma_periods": [5, "10"]}), "ma_periods"),
        (_bad_config(**{"entry.allowed_ma": "5,10,20"}), "allowed_ma"),
        (_bad_config(**{"mainline.potential_share": 0.5}), "potential_share"),
        (_bad_config(**{"position.env_caps.bull.single": -0.5}), "single"),
        (_bad_config(**{"position.env_caps.bull.single": 1.5}), "single"),
        (_bad_config(**{"position.stop_loss_pct": 1.5}), "stop_loss_pct"),
        (_bad_config(**{"position.risk_per_trade": 0}), "risk_per_trade"),
        (
            _bad_config(**{"mainline.consecutive_expand_days": 0}),
            "consecutive_expand_days",
        ),
    ],
)
def test_invalid_config_is_reported_not_crashed(cfg, fragment):
    problems = evaluate.validate_config(cfg)
    assert problems
    assert any(fragment in problem for problem in problems), problems


# --------------------------------------------------------------------------- #
# 示例文件（含反例）与 CLI 契约
# --------------------------------------------------------------------------- #
def test_shipped_reject_example_fails_at_ring_one():
    inp = json.loads(
        (BASE / "examples" / "input_reject_mainline.json").read_text("utf-8")
    )
    result = evaluate.run(inp, CFG)
    assert result["decision"] == "REJECT"
    assert result["stage"] == "环1-主线定方向"


def test_shipped_hold_example_exits():
    inp = json.loads((BASE / "examples" / "input_hold_exit.json").read_text("utf-8"))
    result = evaluate.run(inp, CFG)
    assert result["decision"] == "EXIT"
    assert result["position_cap_pct"] == 0.0


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(BASE),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_success_exit_code_zero():
    proc = _run_cli("--input", "examples/input.json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "BUY_CANDIDATE"


def test_cli_missing_input_exit_code_two():
    proc = _run_cli("--input", "examples/does-not-exist.json")
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["reasons"][0]["code"] == "INPUT_UNREADABLE"
    assert payload["human_confirm_required"] is True


def test_cli_invalid_config_exit_code_two(tmp_path):
    bad_cfg = tmp_path / "bad_config.json"
    bad_cfg.write_text(json.dumps({"data": {}}), encoding="utf-8")
    proc = _run_cli("--input", "examples/input.json", "--config", str(bad_cfg))
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["reasons"][0]["code"] == "CONFIG_INVALID"


def test_cli_wrong_typed_threshold_is_config_error(tmp_path):
    cfg = _bad_config(**{"leader.market_cap_min_yi": "150"})
    bad_cfg = tmp_path / "typed_config.json"
    bad_cfg.write_text(json.dumps(cfg), encoding="utf-8")
    proc = _run_cli("--input", "examples/input.json", "--config", str(bad_cfg))
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["reasons"][0]["code"] == "CONFIG_INVALID"


def test_cli_held_minimal_input(tmp_path):
    inp = tmp_path / "held.json"
    inp.write_text(json.dumps(held_minimal()), encoding="utf-8")
    proc = _run_cli("--input", str(inp))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "HOLD"
    assert CONTRACT_KEYS <= set(payload)


# --------------------------------------------------------------------------- #
# 复审补充：配置窗口、超范围整数、未使用数据块、输出 JSON 合法性
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "cfg, fragment",
    [
        (
            _bad_config(**{"mainline.consecutive_expand_days": 1}),
            "consecutive_expand_days",
        ),
        (
            _bad_config(**{"mainline.consecutive_limit_up_days": 1}),
            "consecutive_limit_up_days",
        ),
        (
            _bad_config(**{"leader.consecutive_turnover_20e8_days": 1}),
            "consecutive_turnover_20e8_days",
        ),
    ],
)
def test_consecutive_window_of_one_is_config_error(cfg, fragment):
    # 「连续」窗口为 1 会让 all(...) 恒真，等于取消该条件
    problems = evaluate.validate_config(cfg)
    assert any(fragment in problem for problem in problems), problems


def test_consecutive_window_of_two_is_valid():
    cfg = _bad_config(**{"mainline.consecutive_expand_days": 2})
    assert evaluate.validate_config(cfg) == []


def test_equal_market_cap_band_is_valid_config():
    cfg = _bad_config(
        **{"leader.market_cap_min_yi": 300, "leader.market_cap_max_yi": 300}
    )
    assert evaluate.validate_config(cfg) == []


def test_absurd_integer_threshold_is_config_error_not_crash(tmp_path):
    cfg = _bad_config(**{"leader.market_cap_min_yi": 10**400})
    assert evaluate.validate_config(cfg)  # 不能抛 OverflowError
    bad_cfg = tmp_path / "huge.json"
    bad_cfg.write_text(
        json.dumps(_bad_config(**{"leader.market_cap_min_yi": 10**400})),
        encoding="utf-8",
    )
    proc = _run_cli("--input", "examples/input.json", "--config", str(bad_cfg))
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["reasons"][0]["code"] == "CONFIG_INVALID"


def test_absurd_integer_price_is_rejected_not_crash(tmp_path):
    inp = tmp_path / "huge_price.json"
    inp.write_text(json.dumps(with_patch(**{"stock.price": 10**400})), encoding="utf-8")
    proc = _run_cli("--input", str(inp))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "REJECT"
    assert "DATA_TYPE_INVALID" in {item["code"] for item in payload["reasons"]}


def test_held_close_below_ma20_wrong_type_is_type_error():
    # 文档口径：缺失/null → WAIT；类型错 → REJECT(DATA_TYPE_INVALID)
    result = run(held_minimal(**{"stock.exit": {"close_below_ma20": "true"}}))
    assert result["decision"] == "REJECT"
    assert result["stage"] == "数据校验"
    assert "DATA_TYPE_INVALID" in reason_codes(result)


def test_unknown_env_reports_data_validation_stage():
    result = run(with_patch(**{"market.env": "sideways"}))
    assert result["stage"] == "数据校验"


def test_entry_mode_ignores_malformed_unused_exit_block():
    # 建仓模式不消费 stock.exit，坏掉的 exit 不应挡住建仓判定
    result = run(with_patch(**{"stock.exit": []}))
    assert result["decision"] == "BUY_CANDIDATE"


def test_held_mode_ignores_malformed_unused_entry_block():
    result = run(held_minimal(**{"stock.entry": []}))
    assert result["decision"] == "HOLD"


def test_nan_name_fields_do_not_break_json_output():
    # 展示型字段被污染时输出 null，而不是把 NaN 写进 JSON
    result = run(with_patch(**{"sector.name": float("nan")}))
    assert result["decision"] == "BUY_CANDIDATE"
    assert result["sector"] is None
    json.dumps(result, ensure_ascii=False, allow_nan=False)

    # 非字符串 symbol 属于类型错误：REJECT，但输出仍是严格 JSON
    result = run(with_patch(**{"stock.symbol": float("nan")}))
    assert result["decision"] == "REJECT"
    assert result["symbol"] is None
    json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))


def test_nan_share_float_is_rejected():
    result = run(
        with_patch(**{"sector.amount_share_history": [0.04, float("nan"), 0.09]})
    )
    assert result["decision"] == "REJECT"
    assert "DATA_TYPE_INVALID" in reason_codes(result)


def test_negative_price_does_not_emit_negative_stop_loss():
    result = run(held_minimal(**{"stock.price": -1}))
    assert result["decision"] == "REJECT"
    assert result["stop_loss_price"] is None


def test_consecutive_window_two_is_configured_shipped_default():
    assert CFG["mainline"]["consecutive_expand_days"] >= 2
    assert CFG["mainline"]["consecutive_limit_up_days"] >= 2
    assert CFG["leader"]["consecutive_turnover_20e8_days"] >= 2


def test_require_flags_can_be_disabled():
    cfg = copy.deepcopy(CFG)
    for key in (
        "require_tier_no_gap",
        "require_adjustment_resilient",
    ):
        cfg["mainline"][key] = False
    for key in (
        "require_above_ma10_long",
        "require_volume_pattern",
        "require_institutional_resonance",
    ):
        cfg["leader"][key] = False
    inp = with_patch(
        **{
            "sector.has_tier_no_gap": None,
            "sector.adjustment_resilient": None,
            "stock.above_ma10_long": None,
            "stock.volume_pattern_ok": None,
            "stock.institutional_resonance": None,
        }
    )
    result = run(inp, cfg=cfg)
    assert result["decision"] == "BUY_CANDIDATE"


def test_missing_data_timestamp_is_missing_field():
    result = run(with_patch(**{"data_timestamp": None}))
    assert result["missing_fields"] == ["data_timestamp"]


def test_data_timestamp_exactly_one_hour_future_is_rejected():
    result = run(with_patch(**{"data_timestamp": "2026-11-11T16:30:00+08:00"}))
    assert result["decision"] == "REJECT"
    assert result["data_age_hours"] == -1.0
    assert result["data_freshness"] == "FUTURE"


def test_entry_mode_rejects_non_object_entry():
    result = run(with_patch(**{"stock.entry": []}))
    assert result["decision"] == "REJECT"
    assert "DATA_TYPE_INVALID" in reason_codes(result)


def test_entry_no_pullback_and_unrecovered_paths():
    result = run(with_patch(**{"stock.entry.pullback_to_ma": 55}))
    assert "ENTRY_NO_PULLBACK" in reason_codes(result)
    result = run(with_patch(**{"stock.entry.intraday_break_recovered": False}))
    assert "ENTRY_NOT_RECOVERED" in reason_codes(result)


def test_leader_is_not_mid_cap_path():
    result = run(with_patch(**{"stock.is_mainline_mid_cap": False}))
    assert "LEADER_NOT_MID_CAP" in reason_codes(result)


def test_mainline_limit_history_short_path():
    result = run(with_patch(**{"sector.limit_up_counts": [7]}))
    assert "MAINLINE_LIMIT_HISTORY_SHORT" in reason_codes(result)


@pytest.mark.parametrize("field", ["breakdown", "laggards_collapsed"])
def test_retreat_blocks_entry(field):
    assert run(with_patch(**{f"sector.{field}": True}))["decision"] == "REJECT"


def test_full_account_blocks_entry():
    d = copy.deepcopy(EXAMPLE)
    d["account"].update(invested_pct=1, cash_pct=0)
    assert run(d)["decision"] == "WAIT"


def test_missing_budget_blocks_entry():
    d = copy.deepcopy(EXAMPLE)
    d["account"].pop("cash_pct")
    assert run(d)["decision"] == "WAIT"


def test_budget_limits_position():
    d = copy.deepcopy(EXAMPLE)
    d["account"].update(invested_pct=.95, cash_pct=.05)
    assert run(d)["position_cap_pct"] == pytest.approx(5)


def test_fixed_stop_does_not_drift():
    d = held_minimal()
    d["account"]["stop_loss_price"] = 10
    d["stock"]["price"] = 9.5
    out = run(d)
    assert out["decision"] == "EXIT"
    assert out["stop_loss_price"] == 10


def test_missing_fixed_stop_not_fabricated():
    d = held_minimal()
    d["stock"]["price"] = 9.5
    assert run(d)["stop_loss_price"] is None


def test_negative_ma_slope_blocks_entry():
    d = copy.deepcopy(EXAMPLE)
    d["stock"]["ma_slopes"]["55"] = -.1
    assert run(d)["decision"] == "WAIT"


def test_fixed_stop_not_blocked_by_missing_ma_exit():
    d = held_minimal()
    d["stock"].pop("exit")
    d["stock"]["price"] = 9
    d["account"]["stop_loss_price"] = 10
    assert run(d)["decision"] == "EXIT"


def test_exit_ma_config_cannot_change_label_only():
    c = copy.deepcopy(CFG)
    c["exit"]["ma_exit"] = 60
    assert evaluate.validate_config(c)

