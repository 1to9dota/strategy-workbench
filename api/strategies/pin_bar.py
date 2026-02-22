"""针形态策略（Pin Bar）

核心逻辑：
- 锤子线（做多信号）：下影线 ≥ 5倍实体，实体 ≤ 20% 总长，出现在下跌后
- 射击之星（做空信号）：上影线 ≥ 5倍实体，实体 ≤ 20% 总长，出现在上涨后

PRD 定义：影线 ≥ 5倍实体，实体 ≤ 20% 总K线长度
"""

from typing import Optional
from api.strategies.base import BaseStrategy, register


@register
class PinBarStrategy(BaseStrategy):
    name = "pin_bar"
    description = "针形态策略：长影线反转信号"
    startup_candle_count = 20

    def get_default_params(self) -> dict:
        return {
            "wick_ratio": 5.0,       # 影线 ≥ 5倍实体
            "body_ratio": 0.2,       # 实体 ≤ 20% 总长
            "trend_lookback": 10,    # 判断前置趋势的K线数
            "stop_loss_pct": 0.02,   # 止损百分比
        }

    def check_signal(self, candles: list[dict], index: int) -> Optional[dict]:
        if index < self.startup_candle_count:
            return None

        c = candles[index]
        o, h, l, cl = c["open"], c["high"], c["low"], c["close"]

        total_range = h - l
        if total_range <= 0:
            return None

        body = abs(cl - o)
        upper_wick = h - max(o, cl)
        lower_wick = min(o, cl) - l

        # 实体占比检查
        if body / total_range > self.params["body_ratio"]:
            return None

        # 避免除零
        if body == 0:
            body = total_range * 0.001  # 十字星视为极小实体

        current_price = cl

        # 锤子线（底部反转做多）：下影线长
        if lower_wick / body >= self.params["wick_ratio"]:
            # 确认前置下跌趋势
            if self._is_downtrend(candles, index):
                stop_loss = l  # 止损设在针的最低点
                return {
                    "direction": "long",
                    "entry_price": current_price,
                    "stop_loss": stop_loss,
                    "enter_tag": "pin_hammer",
                    "strategy_name": self.name,
                }

        # 射击之星（顶部反转做空）：上影线长
        if upper_wick / body >= self.params["wick_ratio"]:
            # 确认前置上涨趋势
            if self._is_uptrend(candles, index):
                stop_loss = h  # 止损设在针的最高点
                return {
                    "direction": "short",
                    "entry_price": current_price,
                    "stop_loss": stop_loss,
                    "enter_tag": "pin_shooting_star",
                    "strategy_name": self.name,
                }

        return None

    def _is_downtrend(self, candles: list[dict], index: int) -> bool:
        """判断前置是否为下跌趋势"""
        lookback = self.params["trend_lookback"]
        start = max(0, index - lookback)
        if start >= index:
            return False
        prices = [c["close"] for c in candles[start:index]]
        if len(prices) < 3:
            return False
        # 简单判断：起点价格高于终点价格
        return prices[0] > prices[-1]

    def _is_uptrend(self, candles: list[dict], index: int) -> bool:
        """判断前置是否为上涨趋势"""
        lookback = self.params["trend_lookback"]
        start = max(0, index - lookback)
        if start >= index:
            return False
        prices = [c["close"] for c in candles[start:index]]
        if len(prices) < 3:
            return False
        return prices[0] < prices[-1]
