"""信号查询 + 确认/跳过 + 下单 API"""

import logging
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from api.auth import get_current_user
from api.database import get_db
from api.schemas import SignalConfirmRequest
from api.ws.manager import ws_manager
from api.exchange.order_manager import execute_signal
from api.exchange.okx_client import is_simulated
from api.config import OKX_FLAG

logger = logging.getLogger("signals_router")

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
async def list_signals(inst_id: str = None, status: str = None,
                       limit: int = 50, _=Depends(get_current_user)):
    """获取信号列表（支持按币种/状态筛选）"""
    db = await get_db()
    signals = await db.get_signals(inst_id=inst_id, status=status, limit=limit)
    return {"signals": signals}


@router.get("/{signal_id}")
async def get_signal(signal_id: int, _=Depends(get_current_user)):
    """获取单个信号详情"""
    db = await get_db()
    signal = await db.get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="信号不存在")
    return signal


@router.post("/{signal_id}/confirm")
async def confirm_signal(signal_id: int, req: SignalConfirmRequest,
                         _=Depends(get_current_user)):
    """确认信号并执行下单

    flag 参数控制模拟/实盘：不传则使用 .env 默认值
    """
    db = await get_db()
    flag = req.flag if req.flag is not None else OKX_FLAG

    # 先更新状态为 confirmed
    await db.update_signal_status(signal_id, "confirmed")

    # 执行下单
    try:
        result = await execute_signal(
            signal_id=signal_id,
            leverage=req.leverage,
            margin_mode=req.margin_mode,
            flag=flag,
        )
    except Exception as e:
        logger.error(f"下单异常: {e}")
        result = {"success": False, "error": str(e)}

    # 推送结果到前端
    status = "executed" if result.get("success") else "confirmed"
    await ws_manager.broadcast("signals", {
        "type": "signal_executed" if result.get("success") else "signal_error",
        "signal_id": signal_id,
        "result": result,
    })

    return {"signal_id": signal_id, **result}


@router.post("/{signal_id}/skip")
async def skip_signal(signal_id: int, _=Depends(get_current_user)):
    """跳过信号"""
    db = await get_db()
    await db.update_signal_status(signal_id, "skipped")

    await ws_manager.broadcast("signals", {
        "type": "signal_status",
        "signal_id": signal_id,
        "status": "skipped",
    })

    return {"status": "skipped", "signal_id": signal_id}


@router.get("/trading/mode")
async def get_trading_mode(_=Depends(get_current_user)):
    """获取当前交易模式"""
    return {
        "flag": OKX_FLAG,
        "mode": "模拟盘" if is_simulated() else "实盘",
    }


# ---- WebSocket 端点 ----

@router.websocket("/ws/signals")
async def signals_ws(websocket: WebSocket, token: str = None):
    """实时信号推送 WebSocket（需通过 query param 传 JWT token）"""
    from api.auth import verify_token
    if not token or not verify_token(token):
        await websocket.close(code=4001, reason="未授权")
        return
    await ws_manager.connect(websocket, "signals")
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "confirm":
                db = await get_db()
                await db.update_signal_status(data["signal_id"], "confirmed")
                await ws_manager.broadcast("signals", {
                    "type": "signal_status",
                    "signal_id": data["signal_id"],
                    "status": "confirmed",
                })
            elif data.get("action") == "skip":
                db = await get_db()
                await db.update_signal_status(data["signal_id"], "skipped")
                await ws_manager.broadcast("signals", {
                    "type": "signal_status",
                    "signal_id": data["signal_id"],
                    "status": "skipped",
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "signals")
