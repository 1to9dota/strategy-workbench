"""MA均线突破策略

核心逻辑：
- 做多信号：连续N根K线收盘价站上长期MA（从下方突破后站稳）
- 做空信号：连续N根K线收盘价跌破长期MA（从上方跌破后确认）

回测验证：MA120 + confirm=3 在 ETH 4H 上 Sharpe 0.40、盈亏比 2.50，
         优于 MA90 的 Sharpe 0.12、盈亏比 1.32。
"""

from typing import Optional
from api.strategies.base import BaseStrategy, register
from api.engine.indicators import calc_sma_series


@register
class MA90Strategy(BaseStrategy):
    name = "ma90"
    description = "MA均线突破策略：连续多根K线站稳/跌破长期MA确认趋势"
    startup_candle_count = 125  # MA120 + 几根缓冲

    def get_default_params(self) -> dict:
        return {
            "ma_period": 120,         # 回测验证 MA120 优于 MA90
            "confirm_bars": 3,        # 连续3根站稳
            "stop_loss_pct": 0.025,   # 止损百分比
        }

    def check_signal(self, candles: list[dict], index: int) -> Optional[dict]:
        if index < self.startup_candle_count:
            return None

        closes = [c["close"] for c in candles[:index + 1]]
        ma_period = self.params["ma_period"]
        confirm_bars = self.params["confirm_bars"]

        # 需要足够的历史数据
        if len(closes) < ma_period + confirm_bars + 1:
            return None

        # 计算 MA90 序列
        ma_series = calc_sma_series(closes, ma_period)

        # 检查最近 confirm_bars 根和之前的状态
        # 做多：之前在 MA 下方，最近 confirm_bars 根全部在 MA 上方
        # 做空：之前在 MA 上方，最近 confirm_bars 根全部在 MA 下方

        current_price = closes[-1]
        current_ma = ma_series[-1]

        if current_ma == 0:
            return None

        # 检查突破前的状态（confirm_bars 之前的那根）
        pre_index = len(closes) - confirm_bars - 1
        if pre_index < ma_period:
            return None

        pre_close = closes[pre_index]
        pre_ma = ma_series[pre_index]

        # 检查最近 confirm_bars 根是否全部站稳/跌破
        recent_closes = closes[-confirm_bars:]
        recent_mas = ma_series[-confirm_bars:]

        all_above = all(c > m for c, m in zip(recent_closes, recent_mas))
        all_below = all(c < m for c, m in zip(recent_closes, recent_mas))

        # 做多：之前在下方，现在连续站上
        if pre_close < pre_ma and all_above:
            stop_loss = current_price * (1 - self.params["stop_loss_pct"])
            return {
                "direction": "long",
                "entry_price": current_price,
                "stop_loss": stop_loss,
                "enter_tag": "ma90_breakout_up",
                "strategy_name": self.name,
            }

        # 做空：之前在上方，现在连续跌破
        if pre_close > pre_ma and all_below:
            stop_loss = current_price * (1 + self.params["stop_loss_pct"])
            return {
                "direction": "short",
                "entry_price": current_price,
                "stop_loss": stop_loss,
                "enter_tag": "ma90_breakout_down",
                "strategy_name": self.name,
            }

        return None
