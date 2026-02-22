"""回测 API"""

import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from api.auth import get_current_user
from api.database import get_db
from api.schemas import BacktestRequest
from api.exchange.data_fetcher import fetch_candles_range, _bar_to_ms

# 导入策略模块以触发 @register 注册
import api.strategies.macd_divergence  # noqa: F401
import api.strategies.pin_bar          # noqa: F401
import api.strategies.ma90             # noqa: F401

from api.engine.backtest import run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("/run")
async def run_backtest_api(
    req: BacktestRequest,
    _user: str = Depends(get_current_user),
):
    """执行回测"""
    db = await get_db()

    # 解析时间范围
    # 明确使用 UTC 时区，避免不同服务器时区差异
    start_ts = int(datetime.fromisoformat(req.start_date).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime.fromisoformat(req.end_date).replace(tzinfo=timezone.utc).timestamp() * 1000)

    # 拉取K线数据（带缓存）
    candles = await fetch_candles_range(req.inst_id, req.bar, start_ts, end_ts)

    if len(candles) < 100:
        return {"error": f"K线数据不足：仅获取 {len(candles)} 根，至少需要100根"}

    # 读取策略参数
    strategy_params = {}
    db_strategies = await db.get_strategies()
    for s in db_strategies:
        params = json.loads(s["params"]) if isinstance(s["params"], str) else s["params"]
        strategy_params[s["id"]] = params

    # 读取系统配置
    settings = await db.get_all_settings()
    position_rules = settings.get("position_rules", {})
    roi_table = settings.get("roi_table", None)
    leverage = settings.get("leverage", 3)

    # 执行回测
    result = await run_backtest(
        candles=candles,
        strategy_ids=req.strategies,
        strategy_params=strategy_params,
        min_strength=req.min_strength,
        initial_capital=req.initial_capital,
        position_rules=position_rules,
        roi_table=roi_table,
        leverage=leverage,
    )

    if "error" in result:
        return result

    # 保存回测结果
    name = req.name or f"{req.inst_id} {req.bar} {req.start_date}~{req.end_date}"
    await db.create_backtest(
        name=name,
        inst_id=req.inst_id,
        bar=req.bar,
        start_date=req.start_date,
        end_date=req.end_date,
        strategies=req.strategies,
        min_strength=req.min_strength,
        result=result["report"],
        trades=result["trades"],
        equity_curve=result["equity_curve"],
    )

    return result


@router.get("/history")
async def get_backtest_history(
    limit: int = 20,
    _user: str = Depends(get_current_user),
):
    """获取回测历史列表"""
    db = await get_db()
    backtests = await db.get_backtests(limit=limit)
    # 解析 result JSON
    for bt in backtests:
        if isinstance(bt.get("result"), str):
            bt["result"] = json.loads(bt["result"])
        if isinstance(bt.get("strategies"), str):
            bt["strategies"] = json.loads(bt["strategies"])
    return backtests


@router.get("/{backtest_id}")
async def get_backtest_detail(
    backtest_id: int,
    _user: str = Depends(get_current_user),
):
    """获取回测详情（含交易明细和资金曲线）"""
    db = await get_db()
    bt = await db.get_backtest(backtest_id)
    if not bt:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="回测记录不存在")

    # 解析 JSON 字段
    for field in ["result", "trades", "equity_curve", "strategies"]:
        if isinstance(bt.get(field), str):
            bt[field] = json.loads(bt[field])

    return bt
