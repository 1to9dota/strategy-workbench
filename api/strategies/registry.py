"""策略注册表"""

# 全局策略注册表：{strategy_id: strategy_class}
strategy_registry: dict[str, type] = {}
