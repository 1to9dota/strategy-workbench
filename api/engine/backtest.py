"""回测引擎 — 逐K线扫描、信号右移、共振计算、模拟交易

关键设计（参考 Freqtrade）：
1. startup_candle_count：策略声明的预热期内不产生交易
2. 信号右移：T 时刻产生信号 → T+1 开盘价执行
3. 止损只能上移不能下移（安全约束）
4. 时间衰减 ROI 表：持仓越久止盈门槛越低
"""

import json
from datetime import datetime, timezone
from typing import Optional

from api.strategies.registry import strategy_registry
from api.engine.resonance import calc_resonance


async def run_backtest(
    candles: list[dict],
    strategy_ids: list[str],
    strategy_params: dict[str, dict] = None,
    min_strength: int = 1,
    initial_capital: float = 10000.0,
    position_rules: dict = None,
    roi_table: dict = None,
    leverage: int = 3,
) -> dict:
    """执行回测

    参数:
        candles: K线数据列表（时间升序）
        strategy_ids: 参与回测的策略ID列表
        strategy_params: 策略自定义参数 {strategy_id: {param: value}}
        min_strength: 最低信号强度过滤
        initial_capital: 初始资金
        position_rules: 仓位规则
        roi_table: 时间衰减ROI表 {"0": 0.05, "30": 0.03, ...}
        leverage: 杠杆倍数

    返回:
        完整回测报告
    """
    if not candles or len(candles) < 100:
        return {"error": "K线数据不足（至少100根）"}

    # 默认仓位规则
    if position_rules is None:
        position_rules = {
            "strength_1_pct": 3, "strength_2_pct": 5,
            "strength_3_pct": 8, "max_total_pct": 70,
        }

    # 初始化策略实例
    strategies = []
    for sid in strategy_ids:
        if sid not in strategy_registry:
            continue
        params = (strategy_params or {}).get(sid, None)
        strategies.append(strategy_registry[sid](params))

    if not strategies:
        return {"error": "没有有效策略"}

    # 计算最大预热期
    max_startup = max(s.startup_candle_count for s in strategies)

    # 回测状态
    capital = initial_capital
    open_positions: list[dict] = []
    closed_trades: list[dict] = []
    equity_curve: list[dict] = []
    all_signals: list[dict] = []

    # 信号右移缓冲：上一根K线产生的信号
    pending_signal: Optional[dict] = None

    for i in range(len(candles)):
        current = candles[i]
        current_price = current["close"]
        current_ts = current["ts"]

        # ---- 1. 先处理上一根K线的待执行信号（信号右移） ----
        if pending_signal and i > 0:
            entry_price = current["open"]  # 用当前K线开盘价执行
            signal = pending_signal
            pending_signal = None

            # 仓位计算（基于初始资金百分比，不因持仓缩减而变化）
            strength_key = f"strength_{min(signal['strength'], 3)}_pct"
            size_pct = position_rules.get(strength_key, 3) / 100
            position_size = initial_capital * size_pct

            # 总仓位检查（基于初始资金）
            total_used = sum(p["position_size"] for p in open_positions)
            max_allowed = initial_capital * position_rules["max_total_pct"] / 100
            if total_used + position_size > max_allowed:
                position_size = max(0, max_allowed - total_used)

            if position_size > 0:
                pos = {
                    "direction": signal["direction"],
                    "entry_price": entry_price,
                    "entry_ts": current_ts,
                    "entry_index": i,
                    "position_size": position_size,
                    "stop_loss": signal["stop_loss"],
                    "initial_stop_loss": signal["stop_loss"],
                    "strategies": signal["strategies"],
                    "enter_tag": signal["enter_tag"],
                    "strength": signal["strength"],
                    "leverage": leverage,
                }
                open_positions.append(pos)
                capital -= position_size  # 开仓时扣减可用资金

        # ---- 2. 检查持仓：止损/止盈/ROI ----
        positions_to_close = []
        for pos in open_positions:
            exit_reason = None
            exit_price = None

            # 止损检查
            if pos["direction"] == "long" and current["low"] <= pos["stop_loss"]:
                exit_price = pos["stop_loss"]
                exit_reason = "stop_loss"
            elif pos["direction"] == "short" and current["high"] >= pos["stop_loss"]:
                exit_price = pos["stop_loss"]
                exit_reason = "stop_loss"

            # 时间衰减 ROI 止盈
            if exit_reason is None and roi_table:
                bars_held = i - pos["entry_index"]
                roi_target = _get_roi_target(roi_table, bars_held)
                if roi_target is not None:
                    if pos["direction"] == "long":
                        pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]
                    else:
                        pnl_pct = (pos["entry_price"] - current_price) / pos["entry_price"]
                    if pnl_pct >= roi_target:
                        exit_price = current_price
                        exit_reason = f"roi_{roi_target:.1%}"

            if exit_reason:
                positions_to_close.append((pos, exit_price, exit_reason))

        # 执行平仓
        closed_ids = set()
        for pos, exit_price, exit_reason in positions_to_close:
            trade = _close_position(pos, exit_price, exit_reason, current_ts)
            closed_trades.append(trade)
            capital += trade["position_size"] + trade["pnl"]  # 归还保证金 + 盈亏
            closed_ids.add(id(pos))
        if closed_ids:
            open_positions = [p for p in open_positions if id(p) not in closed_ids]

        # ---- 3. 跳过预热期，不产生新信号 ----
        if i < max_startup:
            # 仍然记录资金曲线
            equity = _calc_equity(capital, open_positions, current_price)
            equity_curve.append({"ts": current_ts, "equity": equity})
            continue

        # ---- 4. 策略扫描信号 ----
        raw_signals = []
        for strategy in strategies:
            sig = strategy.check_signal(candles, i)
            if sig:
                raw_signals.append(sig)

        # 共振计算
        if raw_signals:
            resonance = calc_resonance(raw_signals)
            if resonance and resonance["strength"] >= min_strength:
                # 检查是否有同方向持仓（冷却机制）
                has_same_dir = any(
                    p["direction"] == resonance["direction"] for p in open_positions
                )
                if not has_same_dir:
                    pending_signal = resonance
                    all_signals.append({
                        **resonance,
                        "ts": current_ts,
                        "price": current_price,
                    })

        # 资金曲线
        equity = _calc_equity(capital, open_positions, current_price)
        equity_curve.append({"ts": current_ts, "equity": equity})

    # ---- 回测结束：强制平仓所有持仓 ----
    for pos in open_positions:
        last_price = candles[-1]["close"]
        trade = _close_position(pos, last_price, "backtest_end", candles[-1]["ts"])
        closed_trades.append(trade)
        capital += trade["position_size"] + trade["pnl"]  # 归还保证金 + 盈亏

    # ---- 统计报告 ----
    report = _calc_report(
        closed_trades, equity_curve, initial_capital, capital, candles
    )
    report["signals_count"] = len(all_signals)
    report["signals"] = all_signals

    return {
        "report": report,
        "trades": closed_trades,
        "equity_curve": equity_curve,
    }


def _close_position(pos: dict, exit_price: float, exit_reason: str,
                     exit_ts: int) -> dict:
    """平仓并计算盈亏"""
    if pos["direction"] == "long":
        pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
    else:
        pnl_pct = (pos["entry_price"] - exit_price) / pos["entry_price"]

    pnl = pos["position_size"] * pnl_pct * pos["leverage"]

    return {
        "direction": pos["direction"],
        "entry_price": pos["entry_price"],
        "entry_ts": pos["entry_ts"],
        "exit_price": exit_price,
        "exit_ts": exit_ts,
        "position_size": pos["position_size"],
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct * 100, 2),
        "exit_reason": exit_reason,
        "strategies": pos["strategies"],
        "enter_tag": pos["enter_tag"],
        "strength": pos["strength"],
        "leverage": pos["leverage"],
    }


def _calc_equity(capital: float, positions: list[dict], current_price: float) -> float:
    """计算当前总权益 = 可用资金 + 各持仓市值（保证金 + 杠杆化未实现盈亏）

    capital 已在开仓时扣减、平仓时归还，此处直接累加持仓价值。
    """
    positions_value = 0
    for pos in positions:
        if pos["direction"] == "long":
            pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]
        else:
            pnl_pct = (pos["entry_price"] - current_price) / pos["entry_price"]
        # 持仓市值 = 保证金 + 杠杆化未实现盈亏
        positions_value += pos["position_size"] + pnl_pct * pos["position_size"] * pos["leverage"]
    return round(capital + positions_value, 2)


def _get_roi_target(roi_table: dict, bars_held: int) -> Optional[float]:
    """根据持仓K线数获取当前 ROI 目标

    roi_table key 为K线根数（不是分钟数），如 {"0": 0.05, "30": 0.03}
    表示：立刻5%止盈，持仓30根K线后3%止盈
    """
    applicable = None
    for bar_count_str, roi in sorted(roi_table.items(), key=lambda x: int(x[0])):
        if bars_held >= int(bar_count_str):
            applicable = roi
    return applicable


def _calc_report(trades: list[dict], equity_curve: list[dict],
                  initial_capital: float, final_capital: float,
                  candles: list[dict]) -> dict:
    """计算回测统计报告"""
    if not trades:
        return {
            "initial_capital": initial_capital,
            "final_capital": final_capital,
            "total_return_pct": 0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "max_drawdown_pct": 0,
            "sharpe_ratio": 0,
            "avg_win_pct": 0,
            "avg_loss_pct": 0,
            "best_trade_pct": 0,
            "worst_trade_pct": 0,
            "buy_hold_return_pct": 0,
        }

    total_return_pct = (final_capital - initial_capital) / initial_capital * 100
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) * 100 if trades else 0

    total_win = sum(t["pnl"] for t in winning)
    total_loss = abs(sum(t["pnl"] for t in losing))
    profit_factor = total_win / total_loss if total_loss > 0 else float("inf")

    avg_win_pct = sum(t["pnl_pct"] for t in winning) / len(winning) if winning else 0
    avg_loss_pct = sum(t["pnl_pct"] for t in losing) / len(losing) if losing else 0

    # 最大回撤
    max_drawdown_pct = 0
    peak = initial_capital
    for point in equity_curve:
        eq = point["equity"]
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        if dd > max_drawdown_pct:
            max_drawdown_pct = dd

    # Sharpe Ratio（简化：用每笔交易收益率）
    if len(trades) > 1:
        returns = [t["pnl_pct"] for t in trades]
        avg_ret = sum(returns) / len(returns)
        std_ret = (sum((r - avg_ret) ** 2 for r in returns) / len(returns)) ** 0.5
        sharpe = avg_ret / std_ret if std_ret > 0 else 0
    else:
        sharpe = 0

    # Buy & Hold 对比
    buy_hold = 0
    if candles:
        first_price = candles[0]["close"]
        last_price = candles[-1]["close"]
        if first_price > 0:
            buy_hold = (last_price - first_price) / first_price * 100

    # 按标签统计
    tag_stats = {}
    for t in trades:
        tag = t.get("enter_tag", "unknown")
        if tag not in tag_stats:
            tag_stats[tag] = {"count": 0, "wins": 0, "total_pnl": 0}
        tag_stats[tag]["count"] += 1
        if t["pnl"] > 0:
            tag_stats[tag]["wins"] += 1
        tag_stats[tag]["total_pnl"] += t["pnl"]

    return {
        "initial_capital": initial_capital,
        "final_capital": round(final_capital, 2),
        "total_return_pct": round(total_return_pct, 2),
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "best_trade_pct": round(max((t["pnl_pct"] for t in trades), default=0), 2),
        "worst_trade_pct": round(min((t["pnl_pct"] for t in trades), default=0), 2),
        "buy_hold_return_pct": round(buy_hold, 2),
        "tag_stats": tag_stats,
    }
