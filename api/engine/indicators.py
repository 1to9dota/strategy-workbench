"""技术指标计算库（复用 TradeGotchi，补充 MA90 和 MACD 序列）

所有函数接受 list[float]，用纯 Python 计算，避免外部依赖。
回测引擎需要完整序列时用 _series 后缀的函数。
"""


def calc_ema(data: list[float], period: int) -> list[float]:
    """指数移动平均线（EMA）完整序列"""
    if not data:
        return []
    ema = [data[0]]
    multiplier = 2 / (period + 1)
    for price in data[1:]:
        ema.append(price * multiplier + ema[-1] * (1 - multiplier))
    return ema


def calc_sma(data: list[float], period: int) -> float:
    """简单移动平均线（SMA），返回最新值"""
    if len(data) < period:
        return 0.0
    return sum(data[-period:]) / period


def calc_sma_series(data: list[float], period: int) -> list[float]:
    """SMA 完整序列（滑动窗口 O(n)，前 period-1 个值用 0 填充）"""
    n = len(data)
    result = [0.0] * n
    if n < period:
        return result
    # 第一个窗口
    window_sum = sum(data[:period])
    result[period - 1] = window_sum / period
    # 滑动
    for i in range(period, n):
        window_sum += data[i] - data[i - period]
        result[i] = window_sum / period
    return result


def calc_rsi(closes: list[float], period: int = 14) -> float:
    """相对强弱指数（RSI），返回 0-100"""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_macd(closes: list[float]) -> dict:
    """MACD 指标（12, 26, 9）
    返回: {line, signal, histogram, golden_cross, death_cross}"""
    if len(closes) < 26:
        return {"line": 0, "signal": 0, "histogram": 0,
                "golden_cross": False, "death_cross": False}
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line_series = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal_series = calc_ema(macd_line_series, 9)
    macd_line = macd_line_series[-1]
    signal_line = signal_series[-1]
    histogram = macd_line - signal_line

    golden_cross = False
    death_cross = False
    if len(macd_line_series) >= 2 and len(signal_series) >= 2:
        prev_hist = macd_line_series[-2] - signal_series[-2]
        if prev_hist <= 0 and histogram > 0:
            golden_cross = True
        elif prev_hist >= 0 and histogram < 0:
            death_cross = True

    return {
        "line": macd_line,
        "signal": signal_line,
        "histogram": histogram,
        "golden_cross": golden_cross,
        "death_cross": death_cross,
    }


def calc_macd_series(closes: list[float]) -> dict:
    """MACD 完整序列，用于背离检测
    返回: {dif: list, dea: list, histogram: list}"""
    if len(closes) < 26:
        n = len(closes)
        return {"dif": [0.0] * n, "dea": [0.0] * n, "histogram": [0.0] * n}
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    dea = calc_ema(dif, 9)
    histogram = [d - s for d, s in zip(dif, dea)]
    return {"dif": dif, "dea": dea, "histogram": histogram}


def calc_bollinger(closes: list[float], period: int = 20) -> dict:
    """布林带（默认20周期，2倍标准差）"""
    if len(closes) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "bandwidth": 0, "percent_b": 50}
    sma = sum(closes[-period:]) / period
    std = (sum((c - sma) ** 2 for c in closes[-period:]) / period) ** 0.5
    upper = sma + 2 * std
    lower = sma - 2 * std
    bandwidth = (upper - lower) / sma * 100 if sma else 0
    percent_b = (closes[-1] - lower) / (upper - lower) * 100 if (upper - lower) else 50
    return {
        "upper": upper, "middle": sma, "lower": lower,
        "bandwidth": bandwidth, "percent_b": percent_b,
    }


def calc_rsi_series(closes: list[float], period: int = 14) -> list[float]:
    """RSI 完整序列（0-100），前 period 个值为 50（中性）"""
    n = len(closes)
    result = [50.0] * n
    if n < period + 1:
        return result
    # 计算每根K线的涨跌幅
    gains = [0.0]
    losses = [0.0]
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    # 滑动窗口计算 RSI
    for i in range(period, n):
        avg_gain = sum(gains[i - period + 1:i + 1]) / period
        avg_loss = sum(losses[i - period + 1:i + 1]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            result[i] = 100 - (100 / (1 + avg_gain / avg_loss))
    return result


def calc_atr_series(highs: list[float], lows: list[float],
                    closes: list[float], period: int = 14) -> list[float]:
    """ATR 完整序列（Wilder 平滑），用于动态止损"""
    n = len(closes)
    result = [0.0] * n
    if n < 2:
        return result
    # True Range 序列
    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    # 第一个 ATR = TR 的简单平均
    if n >= period:
        result[period - 1] = sum(tr[:period]) / period
        # Wilder 平滑：ATR = (prev_ATR * (period-1) + TR) / period
        for i in range(period, n):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def calc_bollinger_series(closes: list[float], period: int = 20) -> dict:
    """布林带完整序列，用于收缩突破检测
    返回: {upper: list, middle: list, lower: list, bandwidth: list}"""
    n = len(closes)
    upper = [0.0] * n
    middle = [0.0] * n
    lower = [0.0] * n
    bandwidth = [0.0] * n
    for i in range(period - 1, n):
        window = closes[i - period + 1:i + 1]
        sma = sum(window) / period
        std = (sum((c - sma) ** 2 for c in window) / period) ** 0.5
        middle[i] = sma
        upper[i] = sma + 2 * std
        lower[i] = sma - 2 * std
        bandwidth[i] = (upper[i] - lower[i]) / sma * 100 if sma > 0 else 0
    return {"upper": upper, "middle": middle, "lower": lower, "bandwidth": bandwidth}


def calc_ma(closes: list[float], period: int) -> float:
    """通用 MA 计算（SMA），返回最新值"""
    return calc_sma(closes, period)


def calc_ma_alignment(closes: list[float]) -> bool:
    """均线多头排列：MA7 > MA14 > MA30"""
    if len(closes) < 30:
        return False
    ma7 = sum(closes[-7:]) / 7
    ma14 = sum(closes[-14:]) / 14
    ma30 = sum(closes[-30:]) / 30
    return ma7 > ma14 > ma30


def calc_volume_ratio(volumes: list[float], lookback: int = 7) -> float:
    """量比 = 最新成交量 / 近N期平均成交量"""
    if not volumes or len(volumes) < lookback:
        return 1.0
    avg_vol = sum(volumes[-lookback:]) / lookback
    if avg_vol == 0:
        return 1.0
    return volumes[-1] / avg_vol


def calc_support_resistance(closes: list[float], lookback: int = 14) -> dict:
    """支撑/阻力位（近N周期最低/最高）"""
    lookback = min(lookback, len(closes))
    if lookback < 2:
        return {"support": 0, "resistance": 0}
    recent = closes[-lookback:]
    return {"support": min(recent), "resistance": max(recent)}


def calc_all(closes: list[float], volumes: list[float]) -> dict:
    """一次性计算所有指标，返回完整快照"""
    rsi = calc_rsi(closes)
    macd = calc_macd(closes)
    bollinger = calc_bollinger(closes)
    ma_alignment = calc_ma_alignment(closes)
    volume_ratio = calc_volume_ratio(volumes)
    support_resistance = calc_support_resistance(closes)

    ma7 = calc_sma(closes, 7)
    ma14 = calc_sma(closes, 14)
    ma30 = calc_sma(closes, 30)
    ma90 = calc_sma(closes, 90)

    return {
        "rsi": rsi,
        "macd_line": macd["line"],
        "macd_signal": macd["signal"],
        "macd_histogram": macd["histogram"],
        "macd_golden_cross": macd["golden_cross"],
        "macd_death_cross": macd["death_cross"],
        "bb_upper": bollinger["upper"],
        "bb_middle": bollinger["middle"],
        "bb_lower": bollinger["lower"],
        "bb_bandwidth": bollinger["bandwidth"],
        "bb_percent_b": bollinger["percent_b"],
        "ma7": ma7, "ma14": ma14, "ma30": ma30, "ma90": ma90,
        "ma_alignment": ma_alignment,
        "volume_ratio": volume_ratio,
        "support": support_resistance["support"],
        "resistance": support_resistance["resistance"],
    }
