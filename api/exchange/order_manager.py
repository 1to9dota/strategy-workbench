"""下单管理 — 信号→仓位计算→OKX下单→止损→记录入库

支持模拟盘/实盘切换，flag 参数透传到 okx_client。
"""

import logging
from api.database import get_db
from api.exchange import okx_client

logger = logging.getLogger("order_manager")


async def calc_position_size(strength: int, flag: str = None) -> dict:
    """根据信号强度计算仓位

    返回 {'size_usdt': float, 'total_used_pct': float, 'allowed': bool}
    """
    db = await get_db()
    settings = await db.get_all_settings()

    rules = settings.get("position_rules", {})
    strength_key = f"strength_{strength}_pct"
    pct = rules.get(strength_key, 3)  # 默认 3%
    max_total = rules.get("max_total_pct", 70)

    # 获取账户余额
    balance = await okx_client.get_balance(flag)
    details = balance.get("details", [])
    usdt_balance = 0
    for d in details:
        if d.get("ccy") == "USDT":
            usdt_balance = float(d.get("availBal", 0))
            break

    if usdt_balance <= 0:
        return {"size_usdt": 0, "total_used_pct": 0, "allowed": False,
                "reason": "USDT 余额不足"}

    # 计算当前已用仓位占比
    positions = await okx_client.get_positions(flag=flag)
    total_margin = sum(float(p.get("margin", 0)) for p in positions)
    total_equity = float(balance.get("totalEq", usdt_balance))
    current_pct = (total_margin / total_equity * 100) if total_equity > 0 else 0

    size_usdt = usdt_balance * pct / 100

    if current_pct + pct > max_total:
        return {"size_usdt": size_usdt, "total_used_pct": current_pct,
                "allowed": False, "reason": f"总仓位将超过 {max_total}% 上限"}

    return {"size_usdt": size_usdt, "total_used_pct": current_pct,
            "allowed": True}


async def calc_contract_size(inst_id: str, usdt_amount: float,
                              price: float, leverage: int,
                              flag: str = None) -> str:
    """将 USDT 金额转换为合约张数

    合约面值 = ctVal（每张多少币）
    张数 = (usdt_amount * leverage) / (price * ctVal)
    """
    instrument = await okx_client.get_instrument(inst_id, flag)
    ct_val = float(instrument.get("ctVal", 0.01))
    lot_sz = float(instrument.get("lotSz", 1))

    # 张数 = 杠杆放大后的名义价值 / 每张价值
    raw_size = (usdt_amount * leverage) / (price * ct_val)
    # 按最小下单量取整
    size = max(lot_sz, int(raw_size / lot_sz) * lot_sz)

    return str(int(size))


async def execute_signal(signal_id: int, leverage: int = 3,
                          margin_mode: str = "isolated",
                          flag: str = None) -> dict:
    """执行信号下单：市价入场 + 止损单 + 记录入库

    flag: "1"=模拟盘, "0"=实盘, None=使用.env默认值
    返回 {'success': bool, 'trade_id': int, 'order': dict, ...}
    """
    db = await get_db()

    # 查信号
    signal = await db.get_signal_by_id(signal_id)

    if not signal:
        return {"success": False, "error": "信号不存在"}

    if signal["status"] != "confirmed":
        return {"success": False, "error": f"信号状态异常: {signal['status']}"}

    inst_id = signal["inst_id"]
    direction = signal["direction"]
    entry_price = signal["entry_price"]
    stop_loss = signal["stop_loss"]
    strength = signal["strength"]

    # 1. 计算仓位
    pos_info = await calc_position_size(strength, flag)
    if not pos_info["allowed"]:
        return {"success": False, "error": pos_info.get("reason", "仓位不允许")}

    size_usdt = pos_info["size_usdt"]

    # 2. 获取最新价格
    ticker = await okx_client.get_ticker(inst_id, flag)
    current_price = float(ticker.get("last", entry_price))

    # 3. 设置杠杆
    await okx_client.set_leverage(inst_id, leverage, margin_mode, flag=flag)

    # 4. 计算张数
    contract_size = await calc_contract_size(
        inst_id, size_usdt, current_price, leverage, flag
    )

    # 5. 市价下单
    side = "buy" if direction == "long" else "sell"
    order = await okx_client.place_market_order(
        inst_id, side, contract_size, margin_mode, flag
    )

    # 6. 设置止损
    sl_side = "sell" if direction == "long" else "buy"
    try:
        sl_order = await okx_client.place_stop_loss(
            inst_id, sl_side, contract_size, stop_loss, margin_mode, flag
        )
    except Exception as e:
        logger.error(f"止损单设置失败（入场单已成交）: {e}")
        sl_order = {"error": str(e)}

    # 7. 交易记录入库
    trade = await db.create_trade(
        signal_id=signal_id,
        inst_id=inst_id,
        direction=direction,
        entry_price=current_price,
        position_size=size_usdt,
        leverage=leverage,
        margin_mode=margin_mode,
    )

    # 8. 更新信号状态
    await db.update_signal_status(signal_id, "executed")

    mode = "模拟盘" if okx_client.is_simulated(flag) else "实盘"
    logger.info(
        f"[{mode}] 下单成功: {inst_id} {direction} "
        f"张数={contract_size} 金额={size_usdt:.2f}USDT "
        f"杠杆={leverage}x 价格={current_price}"
    )

    return {
        "success": True,
        "trade_id": trade["id"],
        "order": order,
        "stop_loss_order": sl_order,
        "mode": mode,
        "size_usdt": size_usdt,
        "contract_size": contract_size,
        "price": current_price,
    }
