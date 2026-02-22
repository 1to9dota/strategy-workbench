#!/bin/bash
# VPS 部署脚本 — 在服务器上运行
set -e

cd /home/ubuntu/strategy-workbench

# 创建 data 目录
mkdir -p data

# 创建 .env（如不存在）
if [ ! -f .env ]; then
  echo "创建 .env 文件..."
  echo "OKX_API_KEY=6dc8f8c4-3139-4b69-99b7-ed13eb5ee586" > .env
  echo "OKX_SECRET=38893A45D4DB92D4086137C56844170B" >> .env
  echo "OKX_PASSPHRASE=1038757Ab..e" >> .env
  echo "OKX_FLAG=1" >> .env
  echo "AUTH_USERNAME=admin" >> .env
  echo "AUTH_PASSWORD=2AxQrdGwhWHjrmb75M2SmQ" >> .env
  echo "JWT_SECRET=cd8085b9a2fba4d93dcc2ec23b86ca4559c85ab8bd65d9c7755734c957f623de" >> .env
  echo "TELEGRAM_BOT_TOKEN=8230576775:AAGsbmAuAZZR3IzLe2ExnA4_8j4zCbNTypc" >> .env
  echo "TELEGRAM_CHAT_ID=8446148055" >> .env
  echo "DB_PATH=data/workbench.db" >> .env
  echo "API_PORT=8000" >> .env
  echo ".env 创建完成"
else
  echo ".env 已存在，跳过"
fi

# 构建并启动
echo "开始构建 Docker 容器..."
docker compose up -d --build

echo "等待服务启动..."
sleep 5

# 健康检查
echo "健康检查..."
curl -s http://localhost:9000/api/health || echo "健康检查失败"

echo ""
echo "容器状态:"
docker compose ps

echo ""
echo "部署完成！访问 http://150.109.76.120:9000"
