"""布林带收缩突破策略（Bollinger Squeeze Breakout）

核心逻辑：
- 加密市场交替出现「盘整」和「爆发」
- 布林带带宽收窄 = 波动率降低 = 市场蓄力
- 当带宽达到近期最低后价格突破布林带上/下轨 → 爆发行情开始
- 配合趋势方向：只做顺势突破

止损设在布林带中轨（20日均线），逻辑：如果突破是假的，价格会回到中轨。
"""

from typing import Optional
from api.strategies.base import BaseStrategy, register
from api.engine.indicators import calc_bollinger_series, calc_sma_series


@register
class BBSqueezeStrategy(BaseStrategy):
    name = "bb_squeeze"
    description = "布林收缩突破：波动率收缩蓄力后突破布林带"
    startup_candle_count = 50  # BB20 + squeeze lookback + 缓冲

    def get_default_params(self) -> dict:
        return {
            "bb_period": 20,
            "squeeze_lookback": 20,     # 近 N 根K线内的带宽最低值
            "squeeze_percentile": 0.3,  # 当前带宽 < 近期最高的 30% 视为收缩
            "ma_period": 120,           # 趋势判断（可选，0=不过滤）
            "stop_loss_pct": 0.025,     # 备用固定止损
        }

    def check_signal(self, candles: list[dict], index: int) -> Optional[dict]:
        if index < self.startup_candle_count:
            return None

        closes = [c["close"] for c in candles[:index + 1]]
        bb_period = self.params["bb_period"]
        squeeze_lookback = self.params["squeeze_lookback"]

        if len(closes) < bb_period + squeeze_lookback:
            return None

        # 计算布林带序列
        bb = calc_bollinger_series(closes, bb_period)
        current_bw = bb["bandwidth"][index]
        current_upper = bb["upper"][index]
        current_lower = bb["lower"][index]
        current_middle = bb["middle"][index]

        if current_bw == 0 or current_middle == 0:
            return None

        # 检查收缩：当前带宽是否处于近期低位
        recent_bw = [bb["bandwidth"][j] for j in range(index - squeeze_lookback, index)
                     if bb["bandwidth"][j] > 0]
        if not recent_bw:
            return None

        max_bw = max(recent_bw)
        threshold = max_bw * self.params["squeeze_percentile"]

        # 带宽必须先收缩到阈值以下（前一根），当前根正在扩张
        prev_bw = bb["bandwidth"][index - 1] if index > 0 else current_bw
        is_squeeze = prev_bw <= threshold
        is_expanding = current_bw > prev_bw

        if not (is_squeeze and is_expanding):
            return None

        current_price = closes[-1]

        # 趋势过滤（可选）
        ma_period = self.params.get("ma_period", 0)
        if ma_period > 0 and len(closes) >= ma_period:
            ma_series = calc_sma_series(closes, ma_period)
            current_ma = ma_series[-1]
            if current_ma > 0:
                # 只做顺势突破
                if current_price > current_upper and current_price < current_ma:
                    return None  # 价格在MA下方，不做多
                if current_price < current_lower and current_price > current_ma:
                    return None  # 价格在MA上方，不做空

        # 突破上轨 → 做多
        if current_price > current_upper:
            stop_loss = current_middle  # 止损在中轨
            return {
                "direction": "long",
                "entry_price": current_price,
                "stop_loss": stop_loss,
                "enter_tag": "bb_squeeze_long",
                "strategy_name": self.name,
            }

        # 突破下轨 → 做空
        if current_price < current_lower:
            stop_loss = current_middle  # 止损在中轨
            return {
                "direction": "short",
                "entry_price": current_price,
                "stop_loss": stop_loss,
                "enter_tag": "bb_squeeze_short",
                "strategy_name": self.name,
            }

        return None
