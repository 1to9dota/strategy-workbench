"""OKX 历史K线数据拉取 + SQLite 缓存（复用 TradeGotchi，增加增量更新）"""

import asyncio
from api.config import OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE, OKX_FLAG


def _get_market_api():
    """获取 OKX Market API 实例"""
    import okx.MarketData as MarketData
    return MarketData.MarketAPI(OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE,
                                flag=OKX_FLAG, debug=False)


async def _fetch_page(inst_id: str, bar: str, after_ts: int = None) -> list[dict]:
    """单页获取 OKX K线数据（最多100根）

    OKX K线格式：[ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
    after_ts: 拉取此时间戳之前的数据（毫秒），用于分页
    """
    api = _get_market_api()
    params = {"instId": inst_id, "bar": bar, "limit": "100"}
    if after_ts:
        params["after"] = str(after_ts)

    # OKX SDK 是同步的，放到线程池执行避免阻塞
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: api.get_candlesticks(**params))

    if result.get("code") != "0":
        raise RuntimeError(f"OKX API 错误: {result.get('msg', '未知错误')}")

    data = result.get("data", [])
    candles = []
    for c in data:
        candles.append({
            "ts": int(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        })
    return candles


async def _fetch_history_page(inst_id: str, bar: str, after_ts: int = None) -> list[dict]:
    """使用历史K线接口拉取更早的数据（超过1440根时用这个）"""
    api = _get_market_api()
    params = {"instId": inst_id, "bar": bar, "limit": "100"}
    if after_ts:
        params["after"] = str(after_ts)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: api.get_history_candlesticks(**params)
    )

    if result.get("code") != "0":
        raise RuntimeError(f"OKX History API 错误: {result.get('msg', '未知错误')}")

    data = result.get("data", [])
    candles = []
    for c in data:
        candles.append({
            "ts": int(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        })
    return candles


async def fetch_candles(inst_id: str, bar: str, limit: int = 500) -> list[dict]:
    """分页获取 OKX 历史K线，带 SQLite 缓存 + 增量更新

    1. 先查 candle_cache 表有没有足够的缓存
    2. 没有则从 OKX API 分页拉取
    3. 写入缓存
    4. 返回统一格式的K线列表（按时间升序）
    """
    from api.database import get_db
    db = await get_db()

    # 尝试从缓存读取
    cached = await db.get_candle_cache(inst_id, bar, limit)
    if len(cached) >= limit:
        return cached[-limit:]

    # 缓存不足，从 API 拉取
    all_candles = []
    after_ts = None
    pages_needed = (limit + 99) // 100

    for i in range(pages_needed):
        # 先尝试普通接口，失败或返空则切历史接口
        page = await _fetch_page(inst_id, bar, after_ts)
        if not page:
            page = await _fetch_history_page(inst_id, bar, after_ts)
        if not page:
            break

        all_candles.extend(page)
        # OKX 返回按时间倒序，最后一条是最早的
        after_ts = page[-1]["ts"]
        if len(all_candles) >= limit:
            break
        # 限流：间隔200ms
        await asyncio.sleep(0.2)

    # 去重（按时间戳）并排序为时间升序
    seen = set()
    unique = []
    for c in all_candles:
        if c["ts"] not in seen:
            seen.add(c["ts"])
            unique.append(c)
    unique.sort(key=lambda x: x["ts"])

    # 写入缓存
    if unique:
        await db.save_candle_cache(inst_id, bar, unique)

    # 合并缓存数据
    all_data = cached + [c for c in unique if c["ts"] not in {x["ts"] for x in cached}]
    all_data.sort(key=lambda x: x["ts"])
    return all_data[-limit:]


async def fetch_candles_range(inst_id: str, bar: str,
                               start_ts: int, end_ts: int) -> list[dict]:
    """拉取指定时间范围的K线（用于回测，支持长时间跨度）

    先查缓存，缺失部分从 API 补充
    """
    from api.database import get_db
    db = await get_db()

    # 先查缓存
    cached = await db.get_candle_cache_range(inst_id, bar, start_ts, end_ts)

    # 估算需要多少根K线（粗略估计）
    bar_ms = _bar_to_ms(bar)
    if bar_ms == 0:
        return cached

    expected_count = (end_ts - start_ts) // bar_ms
    if len(cached) >= expected_count * 0.95:  # 95%以上就认为够了
        return cached

    # 从 API 补充缺失数据
    # 从 end_ts 往前拉（OKX after 参数拉取此时间戳之前的数据）
    all_candles = list(cached)
    after_ts = end_ts + bar_ms

    # 判断是否为历史数据（超过60天前的数据直接用历史接口）
    import time
    now_ms = int(time.time() * 1000)
    is_historical = (now_ms - end_ts) > 60 * 86400 * 1000

    for _ in range(expected_count // 100 + 5):
        if is_historical:
            # 历史数据直接用历史接口，跳过普通接口的无效等待
            page = await _fetch_history_page(inst_id, bar, after_ts)
        else:
            page = await _fetch_page(inst_id, bar, after_ts)
            if not page:
                page = await _fetch_history_page(inst_id, bar, after_ts)
        if not page:
            break

        all_candles.extend(page)
        after_ts = page[-1]["ts"]
        # 拉到的数据已经早于起始时间
        if after_ts <= start_ts:
            break
        await asyncio.sleep(0.2)

    # 去重排序
    seen = set()
    unique = []
    for c in all_candles:
        if c["ts"] not in seen:
            seen.add(c["ts"])
            unique.append(c)
    unique.sort(key=lambda x: x["ts"])

    # 写入缓存
    new_candles = [c for c in unique if c["ts"] not in {x["ts"] for x in cached}]
    if new_candles:
        await db.save_candle_cache(inst_id, bar, new_candles)

    # 过滤到指定范围
    return [c for c in unique if start_ts <= c["ts"] <= end_ts]


def _bar_to_ms(bar: str) -> int:
    """K线周期转毫秒"""
    mapping = {
        "1m": 60_000,
        "3m": 180_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1H": 3_600_000,
        "2H": 7_200_000,
        "4H": 14_400_000,
        "6H": 21_600_000,
        "12H": 43_200_000,
        "1D": 86_400_000,
        "1W": 604_800_000,
    }
    return mapping.get(bar, 0)
