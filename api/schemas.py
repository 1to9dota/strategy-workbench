"""Pydantic 请求/响应模型"""

from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


class BacktestRequest(BaseModel):
    inst_id: str = "BTC-USDT-SWAP"
    bar: str = "4H"
    start_date: str  # ISO 格式: "2023-01-01"
    end_date: str
    strategies: list[str] = ["macd_divergence", "pin_bar", "ma90"]
    min_strength: int = 1
    initial_capital: float = 10000.0
    name: Optional[str] = None


class SignalConfirmRequest(BaseModel):
    leverage: int = 3
    margin_mode: str = "isolated"
    flag: Optional[str] = None  # "1"=模拟盘, "0"=实盘, None=使用.env默认值


class SettingsUpdateRequest(BaseModel):
    key: str
    value: dict | list | str | int | float


class StrategyUpdateRequest(BaseModel):
    enabled: Optional[int] = None
    params: Optional[dict] = None
