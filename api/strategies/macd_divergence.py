"""MACD背离策略

核心逻辑：
- 顶背离（做空信号）：价格创新高，但 DIF 线没有创新高 → 上涨动能衰竭
- 底背离（做多信号）：价格创新低，但 DIF 线没有创新低 → 下跌动能衰竭
- 用3根K线确认峰谷（前后各1根都低于/高于中间那根）
- 新鲜度检查：最新峰/谷必须在最近 max_freshness 根K线内，避免反复触发
"""

from typing import Optional
from api.strategies.base import BaseStrategy, register
from api.engine.indicators import calc_macd_series


@register
class MACDDivergenceStrategy(BaseStrategy):
    name = "macd_divergence"
    description = "MACD背离策略：价格与DIF线背离时产生信号"
    startup_candle_count = 60  # MACD 需要较长预热

    def get_default_params(self) -> dict:
        return {
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
            "divergence_bars": 3,     # 峰谷确认K线数
            "lookback": 30,           # 往前看多少根K线找峰谷
            "min_peak_distance": 5,   # 两个峰/谷之间最少间隔K线数
            "max_freshness": 5,       # 最新峰/谷必须在最近N根内
            "price_div_pct": 0.005,   # 价格背离最小幅度（0.5%）
            "stop_loss_pct": 0.03,    # 止损百分比
        }

    def check_signal(self, candles: list[dict], index: int) -> Optional[dict]:
        if index < self.startup_candle_count:
            return None

        closes = [c["close"] for c in candles[:index + 1]]
        highs = [c["high"] for c in candles[:index + 1]]
        lows = [c["low"] for c in candles[:index + 1]]

        # 计算 MACD 完整序列
        macd = calc_macd_series(closes)
        dif = macd["dif"]

        if len(dif) < 10:
            return None

        lookback = self.params["lookback"]
        confirm = self.params["divergence_bars"]
        current_price = closes[-1]
        data_len = len(closes)

        # 找价格和DIF的峰谷
        price_peaks = self._find_peaks(highs, lookback, confirm)
        price_valleys = self._find_valleys(lows, lookback, confirm)
        dif_peaks = self._find_peaks(dif, lookback, confirm)
        dif_valleys = self._find_valleys(dif, lookback, confirm)

        min_dist = self.params["min_peak_distance"]
        price_div_pct = self.params["price_div_pct"]
        max_freshness = self.params["max_freshness"]

        # 顶背离检测：价格有更高的峰，但 DIF 峰更低
        if len(price_peaks) >= 2 and len(dif_peaks) >= 2:
            pp1, pp2 = price_peaks[-2], price_peaks[-1]
            dp1, dp2 = dif_peaks[-2], dif_peaks[-1]
            # 新鲜度：最新价格峰必须在最近 max_freshness 根内
            is_fresh = (data_len - 1 - pp2["index"]) <= max_freshness + confirm
            if (is_fresh and
                    abs(pp2["index"] - pp1["index"]) >= min_dist and
                    abs(dp2["index"] - dp1["index"]) >= min_dist and
                    pp2["value"] > pp1["value"] * (1 + price_div_pct) and
                    dp2["value"] < dp1["value"]):
                stop_loss = current_price * (1 + self.params["stop_loss_pct"])
                return {
                    "direction": "short",
                    "entry_price": current_price,
                    "stop_loss": stop_loss,
                    "enter_tag": "macd_top_div",
                    "strategy_name": self.name,
                }

        # 底背离检测：价格有更低的谷，但 DIF 谷更高
        if len(price_valleys) >= 2 and len(dif_valleys) >= 2:
            pv1, pv2 = price_valleys[-2], price_valleys[-1]
            dv1, dv2 = dif_valleys[-2], dif_valleys[-1]
            is_fresh = (data_len - 1 - pv2["index"]) <= max_freshness + confirm
            if (is_fresh and
                    abs(pv2["index"] - pv1["index"]) >= min_dist and
                    abs(dv2["index"] - dv1["index"]) >= min_dist and
                    pv2["value"] < pv1["value"] * (1 - price_div_pct) and
                    dv2["value"] > dv1["value"]):
                stop_loss = current_price * (1 - self.params["stop_loss_pct"])
                return {
                    "direction": "long",
                    "entry_price": current_price,
                    "stop_loss": stop_loss,
                    "enter_tag": "macd_bottom_div",
                    "strategy_name": self.name,
                }

        return None

    def _find_peaks(self, data: list[float], lookback: int, confirm: int) -> list[dict]:
        """找峰值（局部最高点，前后各 confirm 根都低于它）"""
        peaks = []
        start = max(0, len(data) - lookback)
        for i in range(start + confirm, len(data) - confirm):
            is_peak = True
            for j in range(1, confirm + 1):
                if data[i - j] >= data[i] or data[i + j] >= data[i]:
                    is_peak = False
                    break
            if is_peak:
                peaks.append({"index": i, "value": data[i]})
        return peaks

    def _find_valleys(self, data: list[float], lookback: int, confirm: int) -> list[dict]:
        """找谷值（局部最低点，前后各 confirm 根都高于它）"""
        valleys = []
        start = max(0, len(data) - lookback)
        for i in range(start + confirm, len(data) - confirm):
            is_valley = True
            for j in range(1, confirm + 1):
                if data[i - j] <= data[i] or data[i + j] <= data[i]:
                    is_valley = False
                    break
            if is_valley:
                valleys.append({"index": i, "value": data[i]})
        return valleys
