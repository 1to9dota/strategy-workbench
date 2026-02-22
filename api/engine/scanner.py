"""实时信号扫描引擎 — 定时检测三个策略 + 共振计算

扫描流程：
1. 拉取最新K线（带缓存）
2. 三个策略分别检测
3. 共振计算
4. 冷却检查（持仓期间同方向不推送）
5. 信号入库 + 推送（Telegram + WebSocket）
"""

import json
import logging
from datetime import datetime, timezone, timedelta

# 导入策略注册
import api.strategies.macd_divergence  # noqa: F401
import api.strategies.pin_bar          # noqa: F401
import api.strategies.ma90             # noqa: F401
import api.strategies.rsi_pullback     # noqa: F401
import api.strategies.bb_squeeze       # noqa: F401

from api.strategies.registry import strategy_registry
from api.engine.resonance import calc_resonance
from api.engine.indicators import calc_sma
from api.exchange.data_fetcher import fetch_candles
from api.database import get_db

logger = logging.getLogger("scanner")


async def scan_pair(inst_id: str, bar: str, min_strength: int = 1) -> dict | None:
    """扫描单个币种+周期，返回共振信号或 None"""
    db = await get_db()

    # 读取启用的策略及其参数
    db_strategies = await db.get_strategies()
    enabled = {s["id"]: json.loads(s["params"]) if isinstance(s["params"], str) else s["params"]
               for s in db_strategies if s["enabled"]}

    if not enabled:
        return None

    # 拉取足够的K线（策略最大预热 + 50根缓冲）
    strategies = []
    for sid, params in enabled.items():
        if sid in strategy_registry:
            strategies.append(strategy_registry[sid](params))

    max_startup = max(s.startup_candle_count for s in strategies) if strategies else 100
    candles = await fetch_candles(inst_id, bar, max_startup + 50)

    if len(candles) < max_startup + 10:
        logger.warning(f"K线不足: {inst_id} {bar} 仅 {len(candles)} 根")
        return None

    # 策略检测最新K线
    index = len(candles) - 1
    raw_signals = []
    for strategy in strategies:
        sig = strategy.check_signal(candles, index)
        if sig:
            raw_signals.append(sig)

    if not raw_signals:
        return None

    # 趋势过滤：价格在长期MA上方只做多，下方只做空
    all_settings = await db.get_all_settings()
    trend_filter_on = all_settings.get("trend_filter", False)
    if trend_filter_on:
        closes = [c["close"] for c in candles]
        trend_ma_period = all_settings.get("trend_ma_period", 200)
        ma_val = calc_sma(closes, trend_ma_period)
        if ma_val > 0:
            current_price = candles[index]["close"]
            raw_signals = [
                s for s in raw_signals
                if (s["direction"] == "long" and current_price > ma_val) or
                   (s["direction"] == "short" and current_price < ma_val)
            ]
            if not raw_signals:
                logger.info(f"趋势过滤: {inst_id} 信号被过滤（逆势）")
                return None

    # 共振计算
    resonance = calc_resonance(raw_signals)
    if not resonance or resonance["strength"] < min_strength:
        return None

    # 冷却检查：6小时内同方向信号去重
    recent = await db.get_signals(inst_id=inst_id, limit=5)
    for r in recent:
        if r["direction"] == resonance["direction"]:
            created = datetime.fromisoformat(r["created_at"])
            if datetime.now(timezone.utc) - created.replace(tzinfo=timezone.utc) < timedelta(hours=6):
                logger.info(f"冷却中: {inst_id} {resonance['direction']} (6h内已有信号)")
                return None

    # 信号入库
    signal = await db.create_signal(
        inst_id=inst_id,
        bar=bar,
        direction=resonance["direction"],
        strength=resonance["strength"],
        strategies=resonance["strategies"],
        entry_price=resonance["entry_price"],
        stop_loss=resonance["stop_loss"],
        enter_tag=resonance["enter_tag"],
    )

    result = {
        **resonance,
        "id": signal["id"],
        "inst_id": inst_id,
        "bar": bar,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"新信号: {inst_id} {bar} {resonance['direction']} "
                f"strength={resonance['strength']} tag={resonance['enter_tag']}")

    return result


async def scan_all() -> list[dict]:
    """扫描所有监控币种和周期，返回所有新信号"""
    db = await get_db()
    settings = await db.get_all_settings()

    pairs = settings.get("monitored_pairs", ["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    bars = settings.get("monitored_bars", ["4H"])
    min_strength = settings.get("min_signal_strength", 1)

    signals = []
    for inst_id in pairs:
        for bar in bars:
            try:
                signal = await scan_pair(inst_id, bar, min_strength)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"扫描失败 {inst_id} {bar}: {e}")

    return signals
