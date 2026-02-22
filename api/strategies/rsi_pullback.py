"""RSI 回调策略

核心逻辑：
- 做多：上升趋势中（价格 > MA120），RSI 从超卖区回升 → 回调结束，顺势入场
- 做空：下降趋势中（价格 < MA120），RSI 从超买区回落 → 反弹结束，顺势入场

优势：比 MA 突破入场价更好，止损更近，盈亏比天然更高。
"""

from typing import Optional
from api.strategies.base import BaseStrategy, register
from api.engine.indicators import calc_sma_series, calc_rsi_series


@register
class RSIPullbackStrategy(BaseStrategy):
    name = "rsi_pullback"
    description = "RSI回调策略：趋势中等待RSI超卖/超买反转入场"
    startup_candle_count = 135  # MA120 + RSI14 + 缓冲

    def get_default_params(self) -> dict:
        return {
            "rsi_period": 14,
            "ma_period": 120,         # 趋势判断用长期MA
            "oversold": 35,           # 上升趋势中的买入区
            "overbought": 65,         # 下降趋势中的卖出区
            "stop_loss_pct": 0.025,   # 止损百分比
        }

    def check_signal(self, candles: list[dict], index: int) -> Optional[dict]:
        if index < self.startup_candle_count:
            return None

        closes = [c["close"] for c in candles[:index + 1]]
        ma_period = self.params["ma_period"]
        rsi_period = self.params["rsi_period"]

        if len(closes) < ma_period + rsi_period:
            return None

        # 计算趋势方向
        ma_series = calc_sma_series(closes, ma_period)
        current_ma = ma_series[-1]
        if current_ma == 0:
            return None

        # 计算 RSI 序列
        rsi_series = calc_rsi_series(closes, rsi_period)
        current_rsi = rsi_series[-1]
        prev_rsi = rsi_series[-2] if len(rsi_series) >= 2 else 50

        current_price = closes[-1]
        oversold = self.params["oversold"]
        overbought = self.params["overbought"]

        # 做多：上升趋势 + RSI 刚从超卖区回升（穿越 oversold 线向上）
        if current_price > current_ma:
            if prev_rsi < oversold and current_rsi >= oversold:
                stop_loss = current_price * (1 - self.params["stop_loss_pct"])
                return {
                    "direction": "long",
                    "entry_price": current_price,
                    "stop_loss": stop_loss,
                    "enter_tag": "rsi_pullback_long",
                    "strategy_name": self.name,
                }

        # 做空：下降趋势 + RSI 刚从超买区回落（穿越 overbought 线向下）
        if current_price < current_ma:
            if prev_rsi > overbought and current_rsi <= overbought:
                stop_loss = current_price * (1 + self.params["stop_loss_pct"])
                return {
                    "direction": "short",
                    "entry_price": current_price,
                    "stop_loss": stop_loss,
                    "enter_tag": "rsi_pullback_short",
                    "strategy_name": self.name,
                }

        return None
