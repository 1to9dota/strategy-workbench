"""策略全面回测 — 新策略 + 引擎升级验证
对比：基准配置 vs 新策略 vs ATR止损/移动止盈 vs 量能过滤
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("AUTH_PASSWORD", "skip_validation_12345678")
os.environ.setdefault("JWT_SECRET", "skip_validation_" + "x" * 32)

from api.database import init_db, get_db
from api.exchange.data_fetcher import fetch_candles_range

# 导入所有策略注册
import api.strategies.macd_divergence  # noqa
import api.strategies.pin_bar          # noqa
import api.strategies.ma90             # noqa
import api.strategies.rsi_pullback     # noqa
import api.strategies.bb_squeeze       # noqa
from api.engine.backtest import run_backtest


async def fetch_data(inst_id: str, bar: str, start_date: str, end_date: str):
    from datetime import datetime, timezone
    start_ts = int(datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc).timestamp() * 1000)
    print(f"  拉取 {inst_id} {bar} {start_date}~{end_date} ...")
    candles = await fetch_candles_range(inst_id, bar, start_ts, end_ts)
    print(f"  获取 {len(candles)} 根K线")
    return candles


def format_report(name: str, result: dict) -> str:
    if "error" in result:
        return f"  {name}: X {result['error']}"

    r = result["report"]
    trades = result["trades"]

    tag_info = ""
    if r.get("tag_stats"):
        tags = []
        for tag, stats in r["tag_stats"].items():
            wr = stats["wins"] / stats["count"] * 100 if stats["count"] > 0 else 0
            tags.append(f"    {tag}: {stats['count']}笔 胜率{wr:.0f}% 盈亏{stats['total_pnl']:.1f}")
        tag_info = "\n" + "\n".join(tags)

    exit_reasons = {}
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
    exit_str = " | ".join(f"{k}:{v}" for k, v in sorted(exit_reasons.items()))

    return (
        f"  {name}:\n"
        f"    收益: {r['total_return_pct']:+.2f}% | "
        f"交易: {r['total_trades']}笔 | "
        f"胜率: {r['win_rate']:.1f}% | "
        f"盈亏比: {r['profit_factor']:.2f} | "
        f"最大回撤: {r['max_drawdown_pct']:.1f}%\n"
        f"    Sharpe: {r['sharpe_ratio']:.2f} | "
        f"平均赢: {r['avg_win_pct']:.2f}% | "
        f"平均亏: {r['avg_loss_pct']:.2f}% | "
        f"最佳: {r['best_trade_pct']:.2f}% | 最差: {r['worst_trade_pct']:.2f}%\n"
        f"    Buy&Hold: {r['buy_hold_return_pct']:.2f}% | "
        f"出场原因: {exit_str}"
        f"{tag_info}"
    )


async def run_test(candles, name, strategy_ids, params=None, min_strength=1,
                   roi_table=None, leverage=3, trend_filter=False, trend_ma_period=200,
                   use_atr_stop=False, atr_stop_multiplier=1.5,
                   trailing_stop_atr=0, volume_filter=False,
                   min_volume_ratio=1.5, volume_lookback=20):
    """跑单次回测"""
    result = await run_backtest(
        candles=candles,
        strategy_ids=strategy_ids,
        strategy_params=params,
        min_strength=min_strength,
        initial_capital=10000.0,
        position_rules={
            "strength_1_pct": 3, "strength_2_pct": 5,
            "strength_3_pct": 8, "max_total_pct": 70,
        },
        roi_table=roi_table,
        leverage=leverage,
        trend_filter=trend_filter,
        trend_ma_period=trend_ma_period,
        use_atr_stop=use_atr_stop,
        atr_stop_multiplier=atr_stop_multiplier,
        trailing_stop_atr=trailing_stop_atr,
        volume_filter=volume_filter,
        min_volume_ratio=min_volume_ratio,
        volume_lookback=volume_lookback,
    )
    print(format_report(name, result))
    return result


async def main():
    await init_db()

    test_cases = [
        ("BTC-USDT-SWAP", "4H", "2024-01-01", "2024-12-31"),
        ("ETH-USDT-SWAP", "4H", "2024-01-01", "2024-12-31"),
        ("BTC-USDT-SWAP", "1H", "2024-06-01", "2024-12-31"),
    ]

    default_roi = {"0": 0.05, "30": 0.03, "60": 0.01, "120": 0}
    new_ma_params = {"ma90": {"ma_period": 120, "confirm_bars": 3}}

    # 基准策略组合
    base_strats = ["macd_divergence", "ma90"]
    # 加入新策略
    all_strats = ["macd_divergence", "ma90", "rsi_pullback", "bb_squeeze"]

    for inst_id, bar, start, end in test_cases:
        print(f"\n{'='*70}")
        print(f"  {inst_id} {bar}  {start} ~ {end}")
        print(f"{'='*70}")

        candles = await fetch_data(inst_id, bar, start, end)
        if len(candles) < 200:
            print(f"  K线不足 {len(candles)} 根，跳过")
            continue

        # ================================================
        # A. 基准：MACD+MA120 + 趋势过滤（上次优化后的配置）
        # ================================================
        print(f"\n{'─'*50}")
        print(f"  A. 基准：MACD+MA120 + 趋势过滤")
        print(f"{'─'*50}")
        await run_test(candles, "基准: MACD+MA120+趋势", base_strats,
                      params=new_ma_params, roi_table=default_roi, trend_filter=True)

        # ================================================
        # B. 新策略单独测试
        # ================================================
        print(f"\n{'─'*50}")
        print(f"  B. 新策略单独表现")
        print(f"{'─'*50}")
        await run_test(candles, "RSI回调 单独", ["rsi_pullback"],
                      roi_table=default_roi, trend_filter=True)
        await run_test(candles, "布林收缩 单独", ["bb_squeeze"],
                      roi_table=default_roi, trend_filter=True)

        # ================================================
        # C. 全策略组合（4策略 + 趋势过滤）
        # ================================================
        print(f"\n{'─'*50}")
        print(f"  C. 全策略组合（4策略）")
        print(f"{'─'*50}")
        await run_test(candles, "4策略+趋势", all_strats,
                      params=new_ma_params, roi_table=default_roi, trend_filter=True)
        await run_test(candles, "4策略+趋势+无ROI", all_strats,
                      params=new_ma_params, roi_table=None, trend_filter=True)

        # ================================================
        # D. ATR 动态止损 vs 固定止损
        # ================================================
        print(f"\n{'─'*50}")
        print(f"  D. ATR 动态止损对比")
        print(f"{'─'*50}")
        await run_test(candles, "固定止损(基准)", all_strats,
                      params=new_ma_params, roi_table=default_roi, trend_filter=True)
        for atr_mult in [1.0, 1.5, 2.0]:
            await run_test(candles, f"ATR止损 x{atr_mult}", all_strats,
                          params=new_ma_params, roi_table=default_roi, trend_filter=True,
                          use_atr_stop=True, atr_stop_multiplier=atr_mult)

        # ================================================
        # E. 移动止盈（Trailing Stop）
        # ================================================
        print(f"\n{'─'*50}")
        print(f"  E. 移动止盈对比")
        print(f"{'─'*50}")
        for trail in [1.5, 2.0, 2.5, 3.0]:
            await run_test(candles, f"移动止盈 ATR x{trail}", all_strats,
                          params=new_ma_params, roi_table=None, trend_filter=True,
                          use_atr_stop=True, atr_stop_multiplier=1.5,
                          trailing_stop_atr=trail)

        # ================================================
        # F. 量能过滤
        # ================================================
        print(f"\n{'─'*50}")
        print(f"  F. 量能过滤对比")
        print(f"{'─'*50}")
        await run_test(candles, "无量能过滤", all_strats,
                      params=new_ma_params, roi_table=default_roi, trend_filter=True)
        for vol_ratio in [1.0, 1.5, 2.0]:
            await run_test(candles, f"量比>{vol_ratio}", all_strats,
                          params=new_ma_params, roi_table=default_roi, trend_filter=True,
                          volume_filter=True, min_volume_ratio=vol_ratio)

        # ================================================
        # G. 最优组合候选
        # ================================================
        print(f"\n{'─'*50}")
        print(f"  G. 最优组合候选")
        print(f"{'─'*50}")
        # ATR止损 + 移动止盈 + 无ROI
        await run_test(candles, "ATR1.5+Trail2.0+无ROI", all_strats,
                      params=new_ma_params, roi_table=None, trend_filter=True,
                      use_atr_stop=True, atr_stop_multiplier=1.5,
                      trailing_stop_atr=2.0)
        # ATR止损 + 移动止盈 + 量能过滤 + 无ROI
        await run_test(candles, "ATR1.5+Trail2.0+量比>1.5+无ROI", all_strats,
                      params=new_ma_params, roi_table=None, trend_filter=True,
                      use_atr_stop=True, atr_stop_multiplier=1.5,
                      trailing_stop_atr=2.0,
                      volume_filter=True, min_volume_ratio=1.5)
        # 保守版：ATR止损 + ROI止盈
        await run_test(candles, "ATR1.5+ROI+量比>1.0", all_strats,
                      params=new_ma_params, roi_table=default_roi, trend_filter=True,
                      use_atr_stop=True, atr_stop_multiplier=1.5,
                      volume_filter=True, min_volume_ratio=1.0)

    print(f"\n{'='*70}")
    print("  全面回测完成")


if __name__ == "__main__":
    asyncio.run(main())
