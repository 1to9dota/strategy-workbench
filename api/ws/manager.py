"""WebSocket 连接管理器 — 推送信号/行情到前端"""

import json
from fastapi import WebSocket
from typing import Optional


class ConnectionManager:
    """管理 WebSocket 连接，支持按频道分组"""

    def __init__(self):
        # {channel: [websocket, ...]}
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str = "default"):
        await websocket.accept()
        if channel not in self.connections:
            self.connections[channel] = []
        self.connections[channel].append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str = "default"):
        if channel in self.connections:
            self.connections[channel] = [
                ws for ws in self.connections[channel] if ws != websocket
            ]

    async def broadcast(self, channel: str, data: dict):
        """向指定频道的所有连接广播消息"""
        if channel not in self.connections:
            return
        dead = []
        for ws in self.connections[channel]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        # 清理断开的连接
        for ws in dead:
            self.connections[channel] = [
                w for w in self.connections[channel] if w != ws
            ]

    async def send_personal(self, websocket: WebSocket, data: dict):
        """向单个连接发送消息"""
        try:
            await websocket.send_json(data)
        except Exception:
            pass


# 全局实例
ws_manager = ConnectionManager()
