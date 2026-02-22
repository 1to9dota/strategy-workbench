"""行情数据 API"""

from fastapi import APIRouter, Depends, Query
from api.auth import get_current_user
from api.exchange.data_fetcher import fetch_candles

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/candles/{inst_id}")
async def get_candles(
    inst_id: str,
    bar: str = Query(default="4H", description="K线周期: 1m/5m/15m/1H/4H/1D"),
    limit: int = Query(default=200, le=3000, description="K线数量"),
    _user: str = Depends(get_current_user),
):
    """获取K线数据（带缓存）"""
    candles = await fetch_candles(inst_id, bar, limit)
    return {"data": candles, "count": len(candles)}
