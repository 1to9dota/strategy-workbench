"""策略基类 — 参考 Freqtrade IStrategy 设计

每个策略需要声明：
- name: 策略唯一标识
- description: 策略描述
- startup_candle_count: 预热K线数量（前N根只计算指标，不产生信号）

信号右移：回测引擎负责将信号 shift(1)，即 T 时刻信号在 T+1 开盘价执行
"""

from abc import ABC, abstractmethod
from typing import Optional
from api.strategies.registry import strategy_registry


class BaseStrategy(ABC):
    name: str = ""
    description: str = ""
    startup_candle_count: int = 30  # 默认30根预热

    def __init__(self, params: dict = None):
        """初始化策略，可传入自定义参数覆盖默认值"""
        self.params = {**self.get_default_params(), **(params or {})}

    @abstractmethod
    def check_signal(self, candles: list[dict], index: int) -> Optional[dict]:
        """检查当前K线是否有信号

        参数:
            candles: 完整K线列表（含历史数据用于指标计算）
            index: 当前检查的K线索引

        返回:
            有信号: {'direction': 'long'/'short', 'entry_price': float,
                     'stop_loss': float, 'enter_tag': str}
            无信号: None

        注意：entry_price 应该用下一根K线的 open（信号右移由回测引擎处理）
              这里返回当前K线的 close 作为参考价
        """
        ...

    @abstractmethod
    def get_default_params(self) -> dict:
        """返回默认参数"""
        ...


def register(cls):
    """装饰器：自动注册策略到全局注册表"""
    strategy_registry[cls.name] = cls
    return cls
