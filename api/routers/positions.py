"""持仓管理 API"""

import logging
from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.database import get_db
from api.exchange import okx_client
from api.config import OKX_FLAG

logger = logging.getLogger("positions_router")

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
async def list_positions(flag: str = None, _=Depends(get_current_user)):
    """获取 OKX 当前持仓"""
    f = flag if flag is not None else OKX_FLAG
    try:
        positions = await okx_client.get_positions(flag=f)
        return {
            "positions": positions,
            "mode": "模拟盘" if okx_client.is_simulated(f) else "实盘",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def list_trades(inst_id: str = None, limit: int = 50,
                      _=Depends(get_current_user)):
    """获取本地交易记录"""
    db = await get_db()
    trades = await db.get_trades(inst_id=inst_id, limit=limit)
    return {"trades": trades}


@router.get("/trades/open")
async def list_open_trades(_=Depends(get_current_user)):
    """获取未平仓交易"""
    db = await get_db()
    trades = await db.get_open_trades()
    return {"trades": trades}


@router.post("/{inst_id}/close")
async def close_position(inst_id: str, flag: str = None,
                          _=Depends(get_current_user)):
    """手动平仓（市价全平）"""
    f = flag if flag is not None else OKX_FLAG
    mode = "模拟盘" if okx_client.is_simulated(f) else "实盘"

    try:
        result = await okx_client.close_position(inst_id, flag=f)

        # 更新本地交易记录
        db = await get_db()
        open_trades = await db.get_open_trades()
        ticker = await okx_client.get_ticker(inst_id, f)
        exit_price = float(ticker.get("last", 0))

        for t in open_trades:
            if t["inst_id"] == inst_id:
                await db.close_trade(t["id"], exit_price, "manual")

        logger.info(f"[{mode}] 手动平仓: {inst_id} @ {exit_price}")
        return {"success": True, "inst_id": inst_id, "mode": mode,
                "exit_price": exit_price}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance")
async def get_balance(flag: str = None, _=Depends(get_current_user)):
    """获取账户余额"""
    f = flag if flag is not None else OKX_FLAG
    try:
        balance = await okx_client.get_balance(f)
        return {
            "balance": balance,
            "mode": "模拟盘" if okx_client.is_simulated(f) else "实盘",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
