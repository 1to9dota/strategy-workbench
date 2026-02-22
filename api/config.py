"""环境变量配置 — 所有敏感信息从 .env 读取"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent.parent / ".env")

# OKX API
OKX_API_KEY = os.getenv("OKX_API_KEY", "")
OKX_SECRET = os.getenv("OKX_SECRET", "")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
OKX_FLAG = os.getenv("OKX_FLAG", "1")  # "1"=模拟盘, "0"=实盘

# JWT 单用户认证（生产环境必须通过 .env 设置强密码）
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 7天过期

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 数据库
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).parent.parent / "data" / "workbench.db"))

# 服务
API_PORT = int(os.getenv("API_PORT", "8000"))

# 启动安全检查：关键配置不能为空或使用弱默认值
_WEAK_PASSWORDS = {"", "changeme", "password", "admin", "123456"}
_WEAK_SECRETS = {"", "your_jwt_secret_change_this", "secret", "changeme"}


def validate_config():
    """检查关键配置，防止使用弱默认值部署。由 FastAPI lifespan 调用。"""
    errors = []
    if AUTH_PASSWORD in _WEAK_PASSWORDS or len(AUTH_PASSWORD) < 8:
        errors.append("AUTH_PASSWORD 未设置或太弱（至少8位），请在 .env 中配置强密码")
    if JWT_SECRET in _WEAK_SECRETS or len(JWT_SECRET) < 32:
        errors.append(
            "JWT_SECRET 未设置或太短（至少32位），请运行: "
            "python -c \"import secrets; print(secrets.token_hex(32))\" 生成随机密钥"
        )
    if errors:
        raise RuntimeError(
            "安全配置错误（请修改 .env 文件）:\n" + "\n".join(f"  - {e}" for e in errors)
        )
