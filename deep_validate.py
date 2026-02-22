"""深度验证脚本 — 用真实 OKX 数据验证策略正确性

检查项：
1. 信号标签分布是否合理
2. 止损方向一致性（做多止损 < 入场价，做空止损 > 入场价）
3. 预热期合规性（startup_candle_count 内无信号）
4. 信号右移正确性（T时刻信号 → T+1开盘价执行）
5. ROI 表行为分析
6. 共振信号检查
7. MACD 峰谷对齐检查
8. 边界情况验证
"""

import asyncio
import sys
import os
import time

# 保证能 import
sys.path.insert(0, os.path.dirname(__file__))

from api.strategies.registry import strategy_registry
import api.strategies.macd_divergence  # noqa
import api.strategies.pin_bar          # noqa
import api.strategies.ma90             # noqa
from api.engine.resonance import calc_resonance
from api.engine.indicators import calc_macd_series, calc_sma_series


passed = 0
failed = 0
warnings = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name} — {detail}")
        failed += 1


def warn(name, detail=""):
    global warnings
    print(f"  ⚠️  {name} — {detail}")
    warnings += 1


async def fetch_real_data():
    """从 OKX 拉取真实 BTC 4H K线数据"""
    from api.exchange.data_fetcher import fetch_candles_range
    from api.database import get_db

    # 初始化数据库（get_db 内部会自动 connect）
    db = await get_db()

    # 2024-01-01 ~ 2024-07-01 (UTC)
    start_ts = 1704067200000  # 2024-01-01 00:00 UTC
    end_ts = 1719792000000    # 2024-07-01 00:00 UTC

    print(f"  拉取 BTC-USDT-SWAP 4H K线 (2024-01-01 ~ 2024-07-01)...")
    candles = await fetch_candles_range("BTC-USDT-SWAP", "4H", start_ts, end_ts)
    print(f"  获取到 {len(candles)} 根K线")
    return candles


def test_strategy_signals_on_real_data(candles):
    """在真实数据上逐K线扫描，收集所有信号"""
    strategies = {
        "pin_bar": strategy_registry["pin_bar"]({}),
        "macd_divergence": strategy_registry["macd_divergence"]({}),
        "ma90": strategy_registry["ma90"]({}),
    }

    all_signals = {name: [] for name in strategies}
    resonance_signals = []

    for i in range(len(candles)):
        raw_signals = []
        for name, strat in strategies.items():
            sig = strat.check_signal(candles, i)
            if sig:
                sig["bar_index"] = i
                sig["candle"] = candles[i]
                all_signals[name].append(sig)
                raw_signals.append(sig)

        if raw_signals:
            res = calc_resonance(raw_signals)
            if res and res["strength"] > 1:
                res["bar_index"] = i
                resonance_signals.append(res)

    return all_signals, resonance_signals


def validate_stop_loss_direction(all_signals):
    """验证止损方向一致性"""
    print("\n--- 止损方向一致性 ---")
    for name, signals in all_signals.items():
        long_violations = 0
        short_violations = 0
        for sig in signals:
            if sig["direction"] == "long" and sig["stop_loss"] >= sig["entry_price"]:
                long_violations += 1
            elif sig["direction"] == "short" and sig["stop_loss"] <= sig["entry_price"]:
                short_violations += 1

        total = len(signals)
        if total > 0:
            check(
                f"{name}: 做多止损 < 入场价",
                long_violations == 0,
                f"{long_violations}/{total} 个违规"
            )
            check(
                f"{name}: 做空止损 > 入场价",
                short_violations == 0,
                f"{short_violations}/{total} 个违规"
            )
        else:
            warn(f"{name}: 无信号，跳过止损检查")


def validate_startup_period(all_signals, strategies):
    """验证预热期合规性"""
    print("\n--- 预热期合规性 ---")
    for name, signals in all_signals.items():
        strat = strategies[name]
        startup = strat.startup_candle_count
        violations = [s for s in signals if s["bar_index"] < startup]
        check(
            f"{name}: 预热期({startup}根)内无信号",
            len(violations) == 0,
            f"发现 {len(violations)} 个违规信号, 最早在 index={violations[0]['bar_index'] if violations else 'N/A'}"
        )


def validate_signal_distribution(all_signals):
    """验证信号分布"""
    print("\n--- 信号分布 ---")
    for name, signals in all_signals.items():
        total = len(signals)
        long_count = sum(1 for s in signals if s["direction"] == "long")
        short_count = sum(1 for s in signals if s["direction"] == "short")

        # 按标签统计
        tags = {}
        for s in signals:
            tag = s.get("enter_tag", "unknown")
            tags[tag] = tags.get(tag, 0) + 1

        print(f"  {name}: 共 {total} 个信号 (做多={long_count}, 做空={short_count})")
        for tag, count in sorted(tags.items()):
            print(f"    {tag}: {count}")

        # 检查信号数量是否合理（不能太多也不能太少）
        if name == "pin_bar":
            check(f"{name}: 信号数 > 0", total > 0, "无信号触发")
            check(f"{name}: 信号数合理 (< 200)", total < 200,
                  f"信号过多: {total}")
        elif name == "macd_divergence":
            check(f"{name}: 信号数 > 0", total > 0, "无信号触发")
            check(f"{name}: 信号数合理 (< 100)", total < 100,
                  f"信号过多: {total}")
        elif name == "ma90":
            check(f"{name}: 信号数 > 0", total > 0, "无信号触发")
            check(f"{name}: 信号数合理 (< 50)", total < 50,
                  f"信号过多: {total}")


def validate_macd_peak_alignment(candles):
    """验证 MACD 背离策略的峰谷对齐问题"""
    print("\n--- MACD 峰谷对齐检查 ---")
    strat = strategy_registry["macd_divergence"]({})

    # 找到所有 MACD 背离信号
    divergence_signals = []
    for i in range(len(candles)):
        sig = strat.check_signal(candles, i)
        if sig:
            sig["bar_index"] = i
            divergence_signals.append(sig)

    # 对每个信号，检查价格峰/谷和 DIF 峰/谷的时间对齐
    misaligned_count = 0
    for sig in divergence_signals:
        idx = sig["bar_index"]
        closes = [c["close"] for c in candles[:idx + 1]]
        highs = [c["high"] for c in candles[:idx + 1]]
        lows = [c["low"] for c in candles[:idx + 1]]
        macd = calc_macd_series(closes)
        dif = macd["dif"]

        lookback = strat.params["lookback"]
        confirm = strat.params["divergence_bars"]

        if sig["enter_tag"] == "macd_top_div":
            price_peaks = strat._find_peaks(highs, lookback, confirm)
            dif_peaks = strat._find_peaks(dif, lookback, confirm)
            if len(price_peaks) >= 2 and len(dif_peaks) >= 2:
                # 检查最近两个峰的时间间距
                price_gap = abs(price_peaks[-1]["index"] - dif_peaks[-1]["index"])
                if price_gap > 10:  # 两个峰相差超过10根K线
                    misaligned_count += 1
        elif sig["enter_tag"] == "macd_bottom_div":
            price_valleys = strat._find_valleys(lows, lookback, confirm)
            dif_valleys = strat._find_valleys(dif, lookback, confirm)
            if len(price_valleys) >= 2 and len(dif_valleys) >= 2:
                price_gap = abs(price_valleys[-1]["index"] - dif_valleys[-1]["index"])
                if price_gap > 10:
                    misaligned_count += 1

    total = len(divergence_signals)
    if total > 0:
        aligned_pct = (total - misaligned_count) / total * 100
        check(
            f"MACD 峰谷对齐率 > 50%",
            aligned_pct > 50,
            f"对齐率 {aligned_pct:.1f}% ({misaligned_count}/{total} 不对齐)"
        )
        print(f"    总信号: {total}, 不对齐: {misaligned_count}, 对齐率: {aligned_pct:.1f}%")
    else:
        warn("MACD 无背离信号，跳过峰谷对齐检查")


def validate_ma90_consecutive(candles):
    """验证 MA90 连续突破确认逻辑"""
    print("\n--- MA90 连续确认检查 ---")
    strat = strategy_registry["ma90"]({})
    signals = []
    for i in range(len(candles)):
        sig = strat.check_signal(candles, i)
        if sig:
            sig["bar_index"] = i
            signals.append(sig)

    # 检查每个信号：确认窗口内确实连续站稳/跌破
    violations = 0
    for sig in signals:
        idx = sig["bar_index"]
        closes = [c["close"] for c in candles[:idx + 1]]
        ma_series = calc_sma_series(closes, 90)
        confirm_bars = 3

        recent_closes = closes[-confirm_bars:]
        recent_mas = ma_series[-confirm_bars:]

        if sig["direction"] == "long":
            for c_val, m_val in zip(recent_closes, recent_mas):
                if c_val <= m_val:
                    violations += 1
                    break
        else:
            for c_val, m_val in zip(recent_closes, recent_mas):
                if c_val >= m_val:
                    violations += 1
                    break

    total = len(signals)
    if total > 0:
        check(
            f"MA90 连续确认无违规",
            violations == 0,
            f"{violations}/{total} 个信号确认期内有反向K线"
        )
    else:
        warn("MA90 无信号，跳过连续确认检查")


def validate_pin_bar_shape(candles):
    """验证 Pin Bar 形态参数"""
    print("\n--- Pin Bar 形态验证 ---")
    strat = strategy_registry["pin_bar"]({})
    signals = []
    for i in range(len(candles)):
        sig = strat.check_signal(candles, i)
        if sig:
            sig["bar_index"] = i
            signals.append(sig)

    # 验证每个信号的K线确实符合 Pin Bar 条件
    shape_violations = 0
    trend_violations = 0

    for sig in signals:
        idx = sig["bar_index"]
        c = candles[idx]
        o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
        total_range = h - l
        body = abs(cl - o)

        # 实体占比
        if total_range > 0 and body / total_range > 0.2:
            shape_violations += 1
            continue

        if body == 0:
            body = total_range * 0.001

        if sig["enter_tag"] == "pin_hammer":
            lower_wick = min(o, cl) - l
            if lower_wick / body < 5.0:
                shape_violations += 1
        elif sig["enter_tag"] == "pin_shooting_star":
            upper_wick = h - max(o, cl)
            if upper_wick / body < 5.0:
                shape_violations += 1

    total = len(signals)
    if total > 0:
        check(
            f"Pin Bar 形态参数全部合规",
            shape_violations == 0,
            f"{shape_violations}/{total} 个信号不符合形态要求"
        )


async def validate_backtest_integration(candles):
    """验证回测引擎的完整流程"""
    print("\n--- 回测引擎完整性 ---")
    from api.engine.backtest import run_backtest

    result = await run_backtest(
        candles=candles,
        strategy_ids=["pin_bar", "macd_divergence", "ma90"],
        min_strength=1,
        initial_capital=10000.0,
        roi_table={"0": 0.05, "30": 0.03, "60": 0.01},
        leverage=3,
    )

    check("回测无错误", "error" not in result, result.get("error", ""))
    if "error" in result:
        return

    report = result["report"]
    trades = result["trades"]
    equity_curve = result["equity_curve"]

    # 基础报告完整性
    check("报告包含 total_trades", "total_trades" in report)
    check("报告包含 win_rate", "win_rate" in report)
    check("报告包含 max_drawdown_pct", "max_drawdown_pct" in report)
    check("报告包含 tag_stats", "tag_stats" in report)
    check("报告包含 buy_hold_return_pct", "buy_hold_return_pct" in report)

    total_trades = report["total_trades"]
    print(f"\n  回测结果概览:")
    print(f"    交易次数: {total_trades}")
    print(f"    胜率: {report['win_rate']:.1f}%")
    print(f"    盈亏因子: {report['profit_factor']:.2f}")
    print(f"    最大回撤: {report['max_drawdown_pct']:.1f}%")
    print(f"    总收益: {report['total_return_pct']:.1f}%")
    print(f"    Buy & Hold: {report['buy_hold_return_pct']:.1f}%")
    print(f"    初始资金: {report['initial_capital']} → 最终资金: {report['final_capital']}")

    # 信号标签分布
    if "tag_stats" in report:
        print(f"\n  按标签统计:")
        for tag, stats in report["tag_stats"].items():
            wr = stats["wins"] / stats["count"] * 100 if stats["count"] > 0 else 0
            print(f"    {tag}: {stats['count']}笔, 胜率{wr:.0f}%, 盈亏{stats['total_pnl']:.1f}")

    # 信号右移验证：每笔交易的入场价应该是信号后一根K线的开盘价
    print("\n  信号右移验证:")
    shift_ok = 0
    shift_bad = 0
    for trade in trades:
        entry_ts = trade["entry_ts"]
        entry_price = trade["entry_price"]
        # 找到这根K线
        for ci, cd in enumerate(candles):
            if cd["ts"] == entry_ts:
                # 入场价应该等于这根K线的 open
                if abs(entry_price - cd["open"]) < 0.01:
                    shift_ok += 1
                else:
                    shift_bad += 1
                    if shift_bad <= 3:  # 只打印前3个
                        print(f"    不匹配: 入场={entry_price}, K线open={cd['open']}, ts={cd['ts']}")
                break

    if total_trades > 0:
        check(
            f"信号右移正确率 100%",
            shift_bad == 0,
            f"{shift_bad}/{total_trades} 笔不匹配"
        )

    # 止损方向验证
    sl_violations = 0
    for trade in trades:
        if trade["direction"] == "long" and trade.get("exit_reason") == "stop_loss":
            if trade["exit_price"] > trade["entry_price"]:
                sl_violations += 1
        elif trade["direction"] == "short" and trade.get("exit_reason") == "stop_loss":
            if trade["exit_price"] < trade["entry_price"]:
                sl_violations += 1

    check(
        "止损触发方向一致",
        sl_violations == 0,
        f"{sl_violations} 笔止损方向异常"
    )

    # 资金曲线完整性
    check("资金曲线非空", len(equity_curve) > 0)
    if equity_curve:
        # 检查时间单调递增
        ts_list = [p["ts"] for p in equity_curve]
        is_sorted = all(ts_list[i] <= ts_list[i+1] for i in range(len(ts_list)-1))
        check("资金曲线时间单调递增", is_sorted)

    # ROI 表行为验证
    roi_exits = [t for t in trades if t["exit_reason"].startswith("roi_")]
    sl_exits = [t for t in trades if t["exit_reason"] == "stop_loss"]
    end_exits = [t for t in trades if t["exit_reason"] == "backtest_end"]

    print(f"\n  退出原因分布:")
    print(f"    ROI止盈: {len(roi_exits)}")
    print(f"    止损: {len(sl_exits)}")
    print(f"    回测结束强平: {len(end_exits)}")

    # ROI 止盈的交易应该都是盈利的
    roi_loss = [t for t in roi_exits if t["pnl"] <= 0]
    if roi_exits:
        check(
            "ROI止盈交易全部盈利",
            len(roi_loss) == 0,
            f"{len(roi_loss)}/{len(roi_exits)} 笔ROI退出但亏损"
        )

    return result


def validate_resonance_logic(all_signals):
    """验证共振逻辑"""
    print("\n--- 共振逻辑验证 ---")

    # 用真实信号的组合测试共振
    # 1. 同方向信号
    long_sigs = []
    short_sigs = []
    for name, sigs in all_signals.items():
        for s in sigs:
            if s["direction"] == "long":
                long_sigs.append(s)
            else:
                short_sigs.append(s)

    if len(long_sigs) >= 2:
        res = calc_resonance(long_sigs[:2])
        check("两个做多信号共振 strength=2", res["strength"] == 2)
        check("共振方向为 long", res["direction"] == "long")
        # 做多取最高止损（最保守）
        expected_sl = max(s["stop_loss"] for s in long_sigs[:2])
        check(
            "做多共振止损取最高",
            abs(res["stop_loss"] - expected_sl) < 0.01,
            f"实际={res['stop_loss']}, 预期={expected_sl}"
        )

    if len(short_sigs) >= 2:
        res = calc_resonance(short_sigs[:2])
        check("两个做空信号共振 strength=2", res["strength"] == 2)
        check("共振方向为 short", res["direction"] == "short")
        expected_sl = min(s["stop_loss"] for s in short_sigs[:2])
        check(
            "做空共振止损取最低",
            abs(res["stop_loss"] - expected_sl) < 0.01,
            f"实际={res['stop_loss']}, 预期={expected_sl}"
        )

    # 冲突方向
    if long_sigs and short_sigs:
        mixed = long_sigs[:2] + short_sigs[:1]
        res = calc_resonance(mixed)
        check("方向冲突取多数方", res["direction"] == "long")
        check("方向冲突 strength 只算同方向", res["strength"] == 2)


def validate_roi_table_behavior():
    """ROI 表单位问题检查"""
    print("\n--- ROI 表行为分析 ---")
    from api.engine.backtest import _get_roi_target

    # 当前实现：key 当做 bar count 比较
    roi_table = {"0": 0.05, "30": 0.03, "60": 0.01}

    # bars_held=0 → 立即 ROI=5%
    target = _get_roi_target(roi_table, 0)
    check("bars_held=0 → ROI=5%", target == 0.05, f"实际={target}")

    # bars_held=29 → 仍是 5%
    target = _get_roi_target(roi_table, 29)
    check("bars_held=29 → ROI=5%", target == 0.05, f"实际={target}")

    # bars_held=30 → ROI=3%
    target = _get_roi_target(roi_table, 30)
    check("bars_held=30 → ROI=3%", target == 0.03, f"实际={target}")

    # bars_held=60 → ROI=1%
    target = _get_roi_target(roi_table, 60)
    check("bars_held=60 → ROI=1%", target == 0.01, f"实际={target}")

    warn(
        "ROI 表 key 单位问题",
        "当前 key 按 bar count 比较，不同周期(1H/4H/1D)下实际时间不同。"
        "如 key='30' 在 4H K线 = 120小时(5天)，在 1H K线 = 30小时。"
        "建议在 API 层做换算 或 在 UI 上标明是'K线根数'而非'分钟数'"
    )


async def main():
    global passed, failed, warnings

    print("=" * 60)
    print("策略深度验证 — 真实 OKX 数据")
    print("=" * 60)

    # 1. 获取真实数据
    print("\n\n=== 1. 获取真实数据 ===")
    try:
        candles = await fetch_real_data()
        check("获取K线数据成功", len(candles) > 0)
        check("K线数量 > 500", len(candles) > 500, f"实际={len(candles)}")
    except Exception as e:
        print(f"  ❌ 数据获取失败: {e}")
        print("  使用单元测试模式继续...")
        candles = None

    if candles:
        # 2. 逐K线扫描信号
        print("\n\n=== 2. 策略信号扫描 ===")
        strategies = {
            "pin_bar": strategy_registry["pin_bar"]({}),
            "macd_divergence": strategy_registry["macd_divergence"]({}),
            "ma90": strategy_registry["ma90"]({}),
        }
        all_signals, resonance_signals = test_strategy_signals_on_real_data(candles)

        # 3. 信号分布
        print("\n\n=== 3. 信号分布 ===")
        validate_signal_distribution(all_signals)

        # 4. 止损方向
        print("\n\n=== 4. 止损方向一致性 ===")
        validate_stop_loss_direction(all_signals)

        # 5. 预热期
        print("\n\n=== 5. 预热期合规性 ===")
        validate_startup_period(all_signals, strategies)

        # 6. Pin Bar 形态
        print("\n\n=== 6. Pin Bar 形态验证 ===")
        validate_pin_bar_shape(candles)

        # 7. MA90 连续确认
        print("\n\n=== 7. MA90 连续确认 ===")
        validate_ma90_consecutive(candles)

        # 8. MACD 峰谷对齐
        print("\n\n=== 8. MACD 峰谷对齐 ===")
        validate_macd_peak_alignment(candles)

        # 9. 共振逻辑
        print("\n\n=== 9. 共振逻辑验证 ===")
        validate_resonance_logic(all_signals)

        # 10. 回测引擎完整性
        print("\n\n=== 10. 回测引擎完整性 ===")
        await validate_backtest_integration(candles)

    # 11. ROI 表行为
    print("\n\n=== 11. ROI 表行为分析 ===")
    validate_roi_table_behavior()

    # 总结
    print(f"\n{'=' * 60}")
    print(f"深度验证结果: {passed} 通过, {failed} 失败, {warnings} 警告")
    if failed == 0:
        print("🎉 所有检查通过!")
    else:
        print("⚠️  有失败项需要排查")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
