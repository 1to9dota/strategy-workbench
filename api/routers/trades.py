"""交易记录 + 盈亏汇总 API"""

import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends

from api.auth import get_current_user
from api.database import get_db

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
async def list_trades(inst_id: str = None, limit: int = 100,
                      _=Depends(get_current_user)):
    """获取交易记录（支持按币种筛选）"""
    db = await get_db()
    trades = await db.get_trades(inst_id=inst_id, limit=limit)
    return {"trades": trades}


@router.get("/summary")
async def trade_summary(_=Depends(get_current_user)):
    """盈亏汇总统计：总体 + 按周 + 按月 + 按策略"""
    db = await get_db()
    trades = await db.get_trades(limit=1000)

    # 只统计已平仓的
    closed = [t for t in trades if t.get("exit_price") is not None]

    if not closed:
        return {"total": _empty_stats(), "weekly": [], "monthly": [],
                "by_strategy": {}}

    # 总体统计
    total = _calc_stats(closed)

    # 按周统计
    weekly = _group_stats(closed, "week")

    # 按月统计
    monthly = _group_stats(closed, "month")

    # 按策略统计（从关联的 signal 拿策略信息）
    signals = await db.get_signals(limit=1000)
    signal_map = {s["id"]: s for s in signals}
    by_strategy = {}
    for t in closed:
        sig = signal_map.get(t.get("signal_id"))
        if not sig:
            continue
        strats = sig.get("strategies", "[]")
        if isinstance(strats, str):
            try:
                strats = json.loads(strats)
            except Exception:
                strats = []
        for s in strats:
            by_strategy.setdefault(s, []).append(t)

    strategy_stats = {name: _calc_stats(ts) for name, ts in by_strategy.items()}

    return {
        "total": total,
        "weekly": weekly,
        "monthly": monthly,
        "by_strategy": strategy_stats,
    }


def _empty_stats():
    return {
        "count": 0, "wins": 0, "losses": 0, "win_rate": 0,
        "total_pnl": 0, "avg_pnl": 0, "best": 0, "worst": 0,
        "profit_factor": 0,
    }


def _calc_stats(trades: list[dict]) -> dict:
    if not trades:
        return _empty_stats()

    pnls = [t.get("pnl", 0) or 0 for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_win = sum(wins) if wins else 0
    total_loss = abs(sum(losses)) if losses else 0

    return {
        "count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl": round(sum(pnls) / len(trades), 2) if trades else 0,
        "best": round(max(pnls), 2) if pnls else 0,
        "worst": round(min(pnls), 2) if pnls else 0,
        "profit_factor": round(total_win / total_loss, 2) if total_loss > 0 else float("inf") if total_win > 0 else 0,
    }


def _group_stats(trades: list[dict], period: str) -> list[dict]:
    """按周/月分组统计"""
    groups: dict[str, list] = {}
    for t in trades:
        created = t.get("created_at", "")
        try:
            dt = datetime.fromisoformat(created)
        except Exception:
            continue

        if period == "week":
            # ISO 周：YYYY-WNN
            key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
        else:
            key = dt.strftime("%Y-%m")

        groups.setdefault(key, []).append(t)

    result = []
    for key in sorted(groups.keys(), reverse=True):
        stats = _calc_stats(groups[key])
        stats["period"] = key
        result.append(stats)

    return result
