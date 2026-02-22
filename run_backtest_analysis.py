"""策略优化对比回测
对比优化前（旧参数）和优化后（新参数 + 趋势过滤）的表现差异。
"""

import asyncio
import json
import sys
import os

# 确保模块路径
sys.path.insert(0, os.path.dirname(__file__))

# 跳过启动安全检查（本地脚本不需要）
os.environ.setdefault("AUTH_PASSWORD", "skip_validation_12345678")
os.environ.setdefault("JWT_SECRET", "skip_validation_" + "x" * 32)

from api.database import init_db, get_db
from api.exchange.data_fetcher import fetch_candles_range, _bar_to_ms

# 导入策略注册
import api.strategies.macd_divergence  # noqa
import api.strategies.pin_bar          # noqa
import api.strategies.ma90             # noqa
from api.engine.backtest import run_backtest


async def fetch_data(inst_id: str, bar: str, start_date: str, end_date: str):
    """拉取K线数据"""
    from datetime import datetime, timezone
    start_ts = int(datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc).timestamp() * 1000)

    print(f"  拉取 {inst_id} {bar} {start_date}~{end_date} ...")
    candles = await fetch_candles_range(inst_id, bar, start_ts, end_ts)
    print(f"  获取 {len(candles)} 根K线")
    return candles


def format_report(name: str, result: dict) -> str:
    """格式化回测报告"""
    if "error" in result:
        return f"  {name}: ❌ {result['error']}"

    r = result["report"]
    trades = result["trades"]

    # 按策略统计
    tag_info = ""
    if r.get("tag_stats"):
        tags = []
        for tag, stats in r["tag_stats"].items():
            wr = stats["wins"] / stats["count"] * 100 if stats["count"] > 0 else 0
            tags.append(f"    {tag}: {stats['count']}笔 胜率{wr:.0f}% 盈亏{stats['total_pnl']:.1f}")
        tag_info = "\n" + "\n".join(tags)

    # 止损/ROI/结束 统计
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
                   roi_table=None, leverage=3, trend_filter=False, trend_ma_period=200):
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
    )
    print(format_report(name, result))
    return result


async def main():
    await init_db()

    # ==========================================
    # 测试场景
    # ==========================================
    test_cases = [
        ("BTC-USDT-SWAP", "4H", "2024-01-01", "2024-12-31"),
        ("ETH-USDT-SWAP", "4H", "2024-01-01", "2024-12-31"),
        ("BTC-USDT-SWAP", "1H", "2024-06-01", "2024-12-31"),
    ]

    default_roi = {"0": 0.05, "30": 0.03, "60": 0.01, "120": 0}

    # 旧参数配置
    old_ma_params = {"ma90": {"ma_period": 90, "confirm_bars": 3}}
    # 新参数配置
    new_ma_params = {"ma90": {"ma_period": 120, "confirm_bars": 3}}

    for inst_id, bar, start, end in test_cases:
        print(f"\n{'='*70}")
        print(f"📊 {inst_id} {bar}  {start} ~ {end}")
        print(f"{'='*70}")

        candles = await fetch_data(inst_id, bar, start, end)
        if len(candles) < 200:
            print(f"  ⚠️  K线不足 {len(candles)} 根，跳过")
            continue

        # ================================================
        # A. 旧配置基准（三策略含 Pin Bar, MA90, 无趋势过滤）
        # ================================================
        print(f"\n{'─'*50}")
        print(f"▶ 旧配置：三策略(含PinBar) + MA90 + 无趋势过滤")
        print(f"{'─'*50}")
        all_old = ["macd_divergence", "pin_bar", "ma90"]
        await run_test(candles, "旧: 三策略组合", all_old, params=old_ma_params,
                      roi_table=default_roi)
        await run_test(candles, "旧: MACD单独", ["macd_divergence"],
                      roi_table=default_roi)
        await run_test(candles, "旧: MA90单独", ["ma90"], params=old_ma_params,
                      roi_table=default_roi)

        # ================================================
        # B. 新配置（去掉 Pin Bar, MA120, 有趋势过滤）
        # ================================================
        print(f"\n{'─'*50}")
        print(f"▶ 新配置：两策略(MACD+MA120) + 趋势过滤MA200")
        print(f"{'─'*50}")
        new_strats = ["macd_divergence", "ma90"]
        await run_test(candles, "新: 两策略组合", new_strats, params=new_ma_params,
                      roi_table=default_roi, trend_filter=True)
        await run_test(candles, "新: MACD+趋势过滤", ["macd_divergence"],
                      roi_table=default_roi, trend_filter=True)
        await run_test(candles, "新: MA120+趋势过滤", ["ma90"], params=new_ma_params,
                      roi_table=default_roi, trend_filter=True)

        # ================================================
        # C. 新配置变体：无ROI止盈（让赢利奔跑）
        # ================================================
        print(f"\n{'─'*50}")
        print(f"▶ 新配置 + 无ROI止盈")
        print(f"{'─'*50}")
        await run_test(candles, "新: 两策略+无ROI", new_strats, params=new_ma_params,
                      roi_table=None, trend_filter=True)

        # ================================================
        # D. 趋势过滤对比（有 vs 无）
        # ================================================
        print(f"\n{'─'*50}")
        print(f"▶ 趋势过滤效果对比")
        print(f"{'─'*50}")
        await run_test(candles, "无过滤: MACD+MA120", new_strats, params=new_ma_params,
                      roi_table=default_roi, trend_filter=False)
        await run_test(candles, "MA200过滤: MACD+MA120", new_strats, params=new_ma_params,
                      roi_table=default_roi, trend_filter=True, trend_ma_period=200)
        await run_test(candles, "MA120过滤: MACD+MA120", new_strats, params=new_ma_params,
                      roi_table=default_roi, trend_filter=True, trend_ma_period=120)

        # ================================================
        # E. MACD 止损优化（ETH上2%更好）
        # ================================================
        print(f"\n{'─'*50}")
        print(f"▶ MACD 止损优化 + 趋势过滤")
        print(f"{'─'*50}")
        for sl in [0.02, 0.03, 0.04]:
            macd_params = {"macd_divergence": {"stop_loss_pct": sl}}
            combined_params = {**macd_params, **new_ma_params}
            await run_test(candles, f"MACD sl={sl:.0%}+MA120+趋势", new_strats,
                          params=combined_params, roi_table=default_roi, trend_filter=True)

    print(f"\n{'='*70}")
    print("✅ 优化对比回测完成")


if __name__ == "__main__":
    asyncio.run(main())
