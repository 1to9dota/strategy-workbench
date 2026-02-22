"""共振强度计算 — 多策略信号叠加确认

共振机制：
- strength 1: 单个策略触发（仓位 3%）
- strength 2: 两个策略同时触发同方向（仓位 5%）
- strength 3: 三个策略同时触发同方向（仓位 8%）
"""

from typing import Optional


def calc_resonance(signals: list[dict]) -> Optional[dict]:
    """计算多个策略信号的共振结果

    参数:
        signals: 各策略的 check_signal 返回值列表（None 的已过滤掉）

    返回:
        共振信号: {
            'direction': 'long'/'short',
            'strength': 1-3,
            'strategies': ['macd_divergence', 'pin_bar'],
            'entry_price': float,  # 取所有信号的平均参考价
            'stop_loss': float,    # 取最保守的止损价
            'enter_tag': str,      # 组合标签
        }
        无信号: None
    """
    if not signals:
        return None

    # 按方向分组
    long_signals = [s for s in signals if s["direction"] == "long"]
    short_signals = [s for s in signals if s["direction"] == "short"]

    # 取信号更多的方向（如果都有，取多的那个）
    if len(long_signals) >= len(short_signals) and long_signals:
        group = long_signals
        direction = "long"
    elif short_signals:
        group = short_signals
        direction = "short"
    else:
        return None

    strength = len(group)
    strategies = [s.get("strategy_name", "unknown") for s in group]
    entry_price = sum(s["entry_price"] for s in group) / len(group)

    # 止损取最保守的：
    # - 做多：止损在入场价下方，取最高值 = 离入场最近 = 最先触发 = 最保守
    # - 做空：止损在入场价上方，取最低值 = 离入场最近 = 最先触发 = 最保守
    if direction == "long":
        stop_loss = max(s["stop_loss"] for s in group)
    else:
        stop_loss = min(s["stop_loss"] for s in group)

    # 组合标签
    tags = [s.get("enter_tag", s.get("strategy_name", "")) for s in group]
    enter_tag = "+".join(tags)

    return {
        "direction": direction,
        "strength": strength,
        "strategies": strategies,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "enter_tag": enter_tag,
    }
