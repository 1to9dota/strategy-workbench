"""策略/合约参数配置 API"""

import json
from fastapi import APIRouter, Depends
from api.auth import get_current_user
from api.database import get_db
from api.schemas import SettingsUpdateRequest, StrategyUpdateRequest

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings(_user: str = Depends(get_current_user)):
    """获取所有系统配置"""
    db = await get_db()
    return await db.get_all_settings()


@router.put("/settings")
async def update_settings(
    req: SettingsUpdateRequest,
    _user: str = Depends(get_current_user),
):
    """更新单个配置项"""
    db = await get_db()
    await db.update_setting(req.key, req.value)
    return {"ok": True}


@router.get("/strategies")
async def get_strategies(_user: str = Depends(get_current_user)):
    """获取所有策略配置"""
    db = await get_db()
    strategies = await db.get_strategies()
    # 解析 params JSON
    for s in strategies:
        s["params"] = json.loads(s["params"]) if isinstance(s["params"], str) else s["params"]
    return strategies


@router.put("/strategies/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    req: StrategyUpdateRequest,
    _user: str = Depends(get_current_user),
):
    """更新策略参数/启停"""
    db = await get_db()
    params_str = json.dumps(req.params) if req.params else None
    await db.update_strategy(strategy_id, enabled=req.enabled, params=params_str)
    return {"ok": True}
