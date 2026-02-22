"""OKX API 封装 — 行情 + 交易，支持模拟盘/实盘切换"""

import asyncio
import logging
from api.config import OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE, OKX_FLAG

logger = logging.getLogger("okx_client")


def _get_trade_api(flag: str = None):
    """获取 OKX Trade API 实例"""
    import okx.Trade as Trade
    f = flag if flag is not None else OKX_FLAG
    return Trade.TradeAPI(OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE,
                          flag=f, debug=False)


def _get_account_api(flag: str = None):
    """获取 OKX Account API 实例"""
    import okx.Account as Account
    f = flag if flag is not None else OKX_FLAG
    return Account.AccountAPI(OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE,
                               flag=f, debug=False)


def _get_public_api(flag: str = None):
    """获取 OKX Public API 实例"""
    import okx.PublicData as PublicData
    f = flag if flag is not None else OKX_FLAG
    return PublicData.PublicAPI(OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE,
                                flag=f, debug=False)


async def _run_sync(func):
    """在线程池中运行同步 OKX SDK 调用"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func)


def is_simulated(flag: str = None) -> bool:
    """判断当前是否模拟盘"""
    f = flag if flag is not None else OKX_FLAG
    return f == "1"


# ---- 账户操作 ----

async def get_balance(flag: str = None) -> dict:
    """获取账户余额"""
    api = _get_account_api(flag)
    result = await _run_sync(lambda: api.get_account_balance())
    if result.get("code") != "0":
        raise RuntimeError(f"获取余额失败: {result.get('msg')}")
    return result["data"][0] if result.get("data") else {}


async def set_leverage(inst_id: str, leverage: int,
                       margin_mode: str = "isolated",
                       pos_side: str = "net", flag: str = None):
    """设置杠杆倍数"""
    api = _get_account_api(flag)
    result = await _run_sync(lambda: api.set_leverage(
        instId=inst_id, lever=str(leverage),
        mgnMode=margin_mode, posSide=pos_side,
    ))
    if result.get("code") != "0":
        logger.warning(f"设置杠杆失败: {result.get('msg')}")
    return result


async def get_positions(inst_id: str = None, flag: str = None) -> list[dict]:
    """获取当前持仓"""
    api = _get_account_api(flag)
    params = {}
    if inst_id:
        params["instId"] = inst_id
    result = await _run_sync(lambda: api.get_positions(**params))
    if result.get("code") != "0":
        raise RuntimeError(f"获取持仓失败: {result.get('msg')}")
    return result.get("data", [])


# ---- 交易操作 ----

async def get_ticker(inst_id: str, flag: str = None) -> dict:
    """获取最新行情（ticker）"""
    import okx.MarketData as MarketData
    f = flag if flag is not None else OKX_FLAG
    api = MarketData.MarketAPI(OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE,
                                flag=f, debug=False)
    result = await _run_sync(lambda: api.get_ticker(instId=inst_id))
    if result.get("code") != "0":
        raise RuntimeError(f"获取行情失败: {result.get('msg')}")
    data = result.get("data", [])
    return data[0] if data else {}


async def get_instrument(inst_id: str, flag: str = None) -> dict:
    """获取合约信息（最小下单量等）"""
    api = _get_public_api(flag)
    inst_type = "SWAP" if "SWAP" in inst_id else "FUTURES"
    result = await _run_sync(lambda: api.get_instruments(
        instType=inst_type, instId=inst_id,
    ))
    if result.get("code") != "0":
        raise RuntimeError(f"获取合约信息失败: {result.get('msg')}")
    data = result.get("data", [])
    return data[0] if data else {}


async def place_market_order(inst_id: str, side: str, size: str,
                              margin_mode: str = "isolated",
                              flag: str = None) -> dict:
    """市价下单

    side: 'buy' (做多) / 'sell' (做空)
    size: 下单数量（张数）
    """
    api = _get_trade_api(flag)
    result = await _run_sync(lambda: api.place_order(
        instId=inst_id,
        tdMode=margin_mode,  # isolated / cross
        side=side,
        ordType="market",
        sz=size,
    ))
    if result.get("code") != "0":
        raise RuntimeError(f"下单失败: {result.get('msg')}")
    data = result.get("data", [])
    if data and data[0].get("sCode") != "0":
        raise RuntimeError(f"下单失败: {data[0].get('sMsg')}")
    return data[0] if data else {}


async def place_stop_loss(inst_id: str, side: str, size: str,
                           stop_price: float,
                           margin_mode: str = "isolated",
                           flag: str = None) -> dict:
    """设置止损单（条件单）

    side: 平仓方向 — 做多持仓的止损用 'sell'，做空的用 'buy'
    stop_price: 触发价格
    """
    api = _get_trade_api(flag)
    result = await _run_sync(lambda: api.place_algo_order(
        instId=inst_id,
        tdMode=margin_mode,
        side=side,
        ordType="conditional",
        sz=size,
        slTriggerPx=str(stop_price),
        slOrdPx="-1",  # -1 表示市价止损
    ))
    if result.get("code") != "0":
        raise RuntimeError(f"止损单失败: {result.get('msg')}")
    data = result.get("data", [])
    if data and data[0].get("sCode") != "0":
        raise RuntimeError(f"止损单失败: {data[0].get('sMsg')}")
    return data[0] if data else {}


async def close_position(inst_id: str, margin_mode: str = "isolated",
                          flag: str = None) -> dict:
    """平仓（市价全平）"""
    api = _get_trade_api(flag)
    result = await _run_sync(lambda: api.close_positions(
        instId=inst_id, mgnMode=margin_mode,
    ))
    if result.get("code") != "0":
        raise RuntimeError(f"平仓失败: {result.get('msg')}")
    return result.get("data", [{}])[0]
