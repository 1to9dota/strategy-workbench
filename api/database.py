"""SQLite 异步数据库层 — aiosqlite 单例 + WAL 模式"""

import json
import aiosqlite
from datetime import datetime, timezone
from typing import Optional
from api.config import DB_PATH

_SCHEMA = """
-- 策略配置（可扩展）
CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    params TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- K线缓存
CREATE TABLE IF NOT EXISTS candle_cache (
    inst_id TEXT NOT NULL,
    bar TEXT NOT NULL,
    ts INTEGER NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (inst_id, bar, ts)
);

-- 信号记录
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inst_id TEXT NOT NULL,
    bar TEXT NOT NULL,
    direction TEXT NOT NULL,
    strength INTEGER NOT NULL,
    strategies TEXT NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    enter_tag TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 交易记录
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER REFERENCES signals(id),
    inst_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    entry_time TEXT NOT NULL,
    exit_price REAL,
    exit_time TEXT,
    exit_reason TEXT,
    position_size REAL NOT NULL,
    pnl REAL,
    pnl_pct REAL,
    leverage INTEGER DEFAULT 3,
    margin_mode TEXT DEFAULT 'isolated',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 回测结果
CREATE TABLE IF NOT EXISTS backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    inst_id TEXT NOT NULL,
    bar TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    strategies TEXT NOT NULL,
    min_strength INTEGER DEFAULT 1,
    result TEXT NOT NULL,
    trades TEXT NOT NULL,
    equity_curve TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 系统配置
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# 默认策略参数
_DEFAULT_STRATEGIES = [
    {
        "id": "macd_divergence",
        "name": "MACD背离",
        "params": json.dumps({
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
            "divergence_bars": 3,  # 3根K线确认峰谷
        }),
    },
    {
        "id": "pin_bar",
        "name": "针形态",
        "enabled": 0,  # 回测验证胜率过低（13-19%），默认关闭
        "params": json.dumps({
            "wick_ratio": 5.0,    # 影线 ≥ 5倍实体
            "body_ratio": 0.2,    # 实体 ≤ 20% 总长
        }),
    },
    {
        "id": "ma90",
        "name": "MA120突破",
        "params": json.dumps({
            "ma_period": 120,     # 回测验证 MA120 优于 MA90
            "confirm_bars": 3,    # 连续3根站稳
        }),
    },
    {
        "id": "rsi_pullback",
        "name": "RSI回调",
        "enabled": 0,  # 单独胜率低（22-35%），但共振确认有价值，保留代码
        "params": json.dumps({
            "rsi_period": 14,
            "ma_period": 120,
            "oversold": 35,
            "overbought": 65,
            "stop_loss_pct": 0.025,
        }),
    },
    {
        "id": "bb_squeeze",
        "name": "布林收缩突破",
        "enabled": 0,  # 回测胜率过低（10-22%），默认关闭
        "params": json.dumps({
            "bb_period": 20,
            "squeeze_lookback": 20,
            "squeeze_percentile": 0.3,
            "ma_period": 120,
            "stop_loss_pct": 0.025,
        }),
    },
]

# 默认系统配置
_DEFAULT_SETTINGS = {
    "position_rules": json.dumps({
        "strength_1_pct": 3,   # 单策略信号：3% 仓位
        "strength_2_pct": 5,   # 双策略共振：5%
        "strength_3_pct": 8,   # 三策略共振：8%
        "max_total_pct": 70,   # 总仓位上限 70%
    }),
    "leverage": json.dumps(3),
    "margin_mode": json.dumps("isolated"),
    "monitored_pairs": json.dumps(["BTC-USDT-SWAP", "ETH-USDT-SWAP"]),
    "monitored_bars": json.dumps(["4H"]),
    "min_signal_strength": json.dumps(1),
    "roi_table": json.dumps({
        "0": 0.05,    # 立刻达到5%止盈
        "30": 0.03,   # 持仓30根K线后3%止盈
        "60": 0.01,   # 持仓60根K线后1%止盈
        "120": 0,     # 持仓120根K线后保本就跑
    }),
    "trend_filter": json.dumps(True),    # 趋势过滤：只允许顺势交易
    "trend_ma_period": json.dumps(200),  # 趋势判断用 MA200
    "volume_filter": json.dumps(True),   # 量能过滤：仅放量时开仓
    "min_volume_ratio": json.dumps(1.0), # 量比阈值（当前量/近期均量）
    "volume_lookback": json.dumps(20),   # 量比回看周期
}


class Database:
    """策略工作台数据库操作封装"""

    def __init__(self):
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        # 确保 data 目录存在
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(DB_PATH))
        self._db.row_factory = aiosqlite.Row
        # WAL 模式：并发读写更好
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        # 初始化默认数据
        await self._init_defaults()

    async def close(self):
        if self._db:
            await self._db.close()

    async def _init_defaults(self):
        """初始化默认策略和配置（不覆盖已有数据）"""
        for s in _DEFAULT_STRATEGIES:
            enabled = s.get("enabled", 1)
            await self._db.execute(
                "INSERT OR IGNORE INTO strategies (id, name, enabled, params) VALUES (?, ?, ?, ?)",
                (s["id"], s["name"], enabled, s["params"]),
            )
        for k, v in _DEFAULT_SETTINGS.items():
            await self._db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (k, v),
            )
        await self._db.commit()

    # ---- K线缓存 ----

    async def save_candle_cache(self, inst_id: str, bar: str, candles: list[dict]):
        """批量写入K线缓存（冲突忽略）"""
        await self._db.executemany(
            """INSERT OR IGNORE INTO candle_cache (inst_id, bar, ts, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(inst_id, bar, c["ts"], c["open"], c["high"], c["low"], c["close"], c["volume"])
             for c in candles],
        )
        await self._db.commit()

    async def get_candle_cache(self, inst_id: str, bar: str, limit: int = 500) -> list[dict]:
        """读取缓存K线（按时间升序，返回最近 limit 根）"""
        cursor = await self._db.execute(
            """SELECT ts, open, high, low, close, volume FROM candle_cache
               WHERE inst_id = ? AND bar = ?
               ORDER BY ts DESC LIMIT ?""",
            (inst_id, bar, limit),
        )
        rows = await cursor.fetchall()
        return [{"ts": r["ts"], "open": r["open"], "high": r["high"],
                 "low": r["low"], "close": r["close"], "volume": r["volume"]}
                for r in reversed(rows)]

    async def get_candle_cache_range(self, inst_id: str, bar: str,
                                     start_ts: int, end_ts: int) -> list[dict]:
        """读取指定时间范围的缓存K线"""
        cursor = await self._db.execute(
            """SELECT ts, open, high, low, close, volume FROM candle_cache
               WHERE inst_id = ? AND bar = ? AND ts >= ? AND ts <= ?
               ORDER BY ts ASC""",
            (inst_id, bar, start_ts, end_ts),
        )
        rows = await cursor.fetchall()
        return [{"ts": r["ts"], "open": r["open"], "high": r["high"],
                 "low": r["low"], "close": r["close"], "volume": r["volume"]}
                for r in rows]

    async def get_latest_cached_ts(self, inst_id: str, bar: str) -> Optional[int]:
        """获取缓存中最新的时间戳，用于增量拉取"""
        cursor = await self._db.execute(
            "SELECT MAX(ts) as max_ts FROM candle_cache WHERE inst_id = ? AND bar = ?",
            (inst_id, bar),
        )
        row = await cursor.fetchone()
        return row["max_ts"] if row and row["max_ts"] else None

    # ---- 信号 CRUD ----

    async def create_signal(self, inst_id: str, bar: str, direction: str,
                            strength: int, strategies: list[str],
                            entry_price: float, stop_loss: float,
                            enter_tag: str = None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.execute(
            """INSERT INTO signals (inst_id, bar, direction, strength, strategies,
                                    entry_price, stop_loss, enter_tag, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (inst_id, bar, direction, strength, json.dumps(strategies),
             entry_price, stop_loss, enter_tag, now),
        )
        await self._db.commit()
        return {"id": cursor.lastrowid, "strength": strength, "direction": direction}

    async def get_signals(self, inst_id: str = None, status: str = None,
                          limit: int = 50) -> list[dict]:
        conditions = []
        params = []
        if inst_id:
            conditions.append("inst_id = ?")
            params.append(inst_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        cursor = await self._db.execute(
            f"SELECT * FROM signals {where} ORDER BY id DESC LIMIT ?",
            params + [limit],
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_signal_by_id(self, signal_id: int) -> Optional[dict]:
        """按 ID 查询单个信号"""
        cursor = await self._db.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_signal_status(self, signal_id: int, status: str):
        await self._db.execute(
            "UPDATE signals SET status = ? WHERE id = ?", (status, signal_id),
        )
        await self._db.commit()

    # ---- 交易 CRUD ----

    async def create_trade(self, signal_id: int, inst_id: str, direction: str,
                           entry_price: float, position_size: float,
                           leverage: int = 3, margin_mode: str = "isolated") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.execute(
            """INSERT INTO trades (signal_id, inst_id, direction, entry_price,
                                   entry_time, position_size, leverage, margin_mode, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal_id, inst_id, direction, entry_price, now,
             position_size, leverage, margin_mode, now),
        )
        await self._db.commit()
        return {"id": cursor.lastrowid}

    async def close_trade(self, trade_id: int, exit_price: float,
                          exit_reason: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        # 先查入场价算盈亏
        trade = await self.get_trade(trade_id)
        if not trade:
            return None
        if trade["direction"] == "long":
            pnl_pct = (exit_price - trade["entry_price"]) / trade["entry_price"] * 100
        else:
            pnl_pct = (trade["entry_price"] - exit_price) / trade["entry_price"] * 100
        pnl = trade["position_size"] * pnl_pct / 100 * trade["leverage"]
        await self._db.execute(
            """UPDATE trades SET exit_price = ?, exit_time = ?, exit_reason = ?,
                                 pnl = ?, pnl_pct = ? WHERE id = ?""",
            (exit_price, now, exit_reason, pnl, pnl_pct, trade_id),
        )
        await self._db.commit()
        return await self.get_trade(trade_id)

    async def get_trade(self, trade_id: int) -> Optional[dict]:
        cursor = await self._db.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_trades(self, inst_id: str = None, limit: int = 50) -> list[dict]:
        if inst_id:
            cursor = await self._db.execute(
                "SELECT * FROM trades WHERE inst_id = ? ORDER BY id DESC LIMIT ?",
                (inst_id, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_open_trades(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM trades WHERE exit_price IS NULL ORDER BY id DESC",
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- 回测 CRUD ----

    async def create_backtest(self, name: str, inst_id: str, bar: str,
                              start_date: str, end_date: str,
                              strategies: list[str], min_strength: int,
                              result: dict, trades: list[dict],
                              equity_curve: list[dict] = None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.execute(
            """INSERT INTO backtests (name, inst_id, bar, start_date, end_date,
                                      strategies, min_strength, result, trades,
                                      equity_curve, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, inst_id, bar, start_date, end_date,
             json.dumps(strategies), min_strength, json.dumps(result),
             json.dumps(trades), json.dumps(equity_curve or []), now),
        )
        await self._db.commit()
        return {"id": cursor.lastrowid}

    async def get_backtest(self, backtest_id: int) -> Optional[dict]:
        cursor = await self._db.execute("SELECT * FROM backtests WHERE id = ?", (backtest_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_backtests(self, limit: int = 20) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, name, inst_id, bar, start_date, end_date, strategies, "
            "min_strength, result, created_at FROM backtests ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- 策略配置 ----

    async def get_strategies(self) -> list[dict]:
        cursor = await self._db.execute("SELECT * FROM strategies ORDER BY id")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_strategy(self, strategy_id: str, enabled: int = None,
                              params: str = None):
        sets, vals = [], []
        if enabled is not None:
            sets.append("enabled = ?")
            vals.append(enabled)
        if params is not None:
            sets.append("params = ?")
            vals.append(params)
        if sets:
            vals.append(strategy_id)
            await self._db.execute(
                f"UPDATE strategies SET {', '.join(sets)} WHERE id = ?", vals,
            )
            await self._db.commit()

    # ---- 系统配置 ----

    async def get_setting(self, key: str) -> Optional[str]:
        cursor = await self._db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,),
        )
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def get_all_settings(self) -> dict:
        cursor = await self._db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    async def update_setting(self, key: str, value):
        await self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        await self._db.commit()


# ---- 全局单例 ----

_db_instance: Optional[Database] = None


async def init_db():
    global _db_instance
    _db_instance = Database()
    await _db_instance.connect()
    return _db_instance


async def get_db() -> Database:
    if _db_instance is None:
        await init_db()
    return _db_instance
