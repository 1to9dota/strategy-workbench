"""FastAPI 应用入口 — 含 APScheduler 定时扫描 + Telegram Bot"""

import time
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.database import init_db
from api.auth import authenticate
from api.schemas import LoginRequest, LoginResponse
from api.routers import market, settings, backtest, signals, positions, trades

logger = logging.getLogger("main")

# ---- 登录限流 ----
_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_MAX_ATTEMPTS = 5           # 最多连续失败次数
_LOGIN_LOCKOUT_SECONDS = 300      # 锁定时间（5分钟）


def _check_login_rate_limit(client_ip: str) -> int:
    """检查登录频率限制，返回剩余锁定秒数（0 表示未锁定）"""
    now = time.time()
    attempts = _login_attempts.get(client_ip, [])
    # 清理过期记录
    attempts = [t for t in attempts if now - t < _LOGIN_LOCKOUT_SECONDS]
    if not attempts:
        _login_attempts.pop(client_ip, None)
        return 0
    _login_attempts[client_ip] = attempts
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        oldest = attempts[0]
        return int(_LOGIN_LOCKOUT_SECONDS - (now - oldest))
    return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库、定时扫描、Telegram Bot"""
    # 安全配置检查（在 lifespan 中运行，不影响测试和工具脚本导入）
    from api.config import validate_config
    validate_config()

    db = await init_db()

    # 启动 Telegram Bot
    from api.bot.telegram_bot import start_bot, stop_bot
    await start_bot()

    # 启动 APScheduler 定时扫描
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from api.engine.scanner import scan_all
    from api.bot.telegram_bot import send_signal
    from api.ws.manager import ws_manager

    scheduler = AsyncIOScheduler()

    async def scheduled_scan():
        """定时扫描任务：扫描所有监控币种，推送信号"""
        try:
            new_signals = await scan_all()
            for sig in new_signals:
                # 推送到 Telegram
                await send_signal(sig)
                # 推送到 WebSocket 前端
                await ws_manager.broadcast("signals", {
                    "type": "new_signal",
                    "signal": sig,
                })
            if new_signals:
                logger.info(f"定时扫描完成: {len(new_signals)} 个新信号")
        except Exception as e:
            logger.error(f"定时扫描异常: {e}")

    # 每分钟扫描一次
    scheduler.add_job(scheduled_scan, "interval", minutes=1, id="signal_scanner")
    scheduler.start()
    logger.info("APScheduler 定时扫描已启动（每分钟）")

    yield

    # 关闭
    scheduler.shutdown(wait=False)
    await stop_bot()
    await db.close()


app = FastAPI(
    title="策略工作台 API",
    description="私人策略工作台后端服务",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（从环境变量读取允许的 origins）
import os
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# 注册路由
app.include_router(market.router)
app.include_router(settings.router)
app.include_router(backtest.router)
app.include_router(signals.router)
app.include_router(positions.router)
app.include_router(trades.router)


# ---- 认证端点 ----

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request):
    """登录（单用户JWT，含暴力破解限流）"""
    from fastapi import HTTPException

    # 优先从反向代理头获取真实 IP
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    remaining = _check_login_rate_limit(client_ip)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail=f"登录尝试过多，请 {remaining} 秒后重试",
        )

    token = authenticate(req.username, req.password)
    if not token:
        _login_attempts[client_ip].append(time.time())
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 登录成功后清除失败记录
    _login_attempts.pop(client_ip, None)
    return LoginResponse(token=token, username=req.username)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
