// 后端 API 客户端

import type { BacktestRequest, BacktestResult, BacktestHistory, Strategy, Candle, Signal, Settings } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    throw new Error("未登录");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API 错误: ${res.status}`);
  }

  return res.json();
}

// 认证
export async function login(username: string, password: string) {
  const data = await apiFetch<{ token: string; username: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  localStorage.setItem("token", data.token);
  return data;
}

export function logout() {
  localStorage.removeItem("token");
  window.location.href = "/login";
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

// 回测
export async function runBacktest(req: BacktestRequest): Promise<BacktestResult> {
  return apiFetch("/api/backtest/run", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getBacktestHistory(limit = 20): Promise<BacktestHistory[]> {
  return apiFetch(`/api/backtest/history?limit=${limit}`);
}

export async function getBacktestDetail(id: number) {
  return apiFetch(`/api/backtest/${id}`);
}

// 行情
export async function getCandles(instId: string, bar: string, limit = 200): Promise<{ data: Candle[]; count: number }> {
  return apiFetch(`/api/market/candles/${encodeURIComponent(instId)}?bar=${bar}&limit=${limit}`);
}

// 策略
export async function getStrategies(): Promise<Strategy[]> {
  return apiFetch("/api/strategies");
}

export async function updateStrategy(id: string, data: { enabled?: number; params?: Record<string, number> }) {
  return apiFetch(`/api/strategies/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// 配置
export async function getSettings(): Promise<Settings> {
  return apiFetch<Settings>("/api/settings");
}

export async function updateSettings(key: string, value: unknown) {
  return apiFetch("/api/settings", {
    method: "PUT",
    body: JSON.stringify({ key, value }),
  });
}

// 信号
export async function getSignals(params?: {
  inst_id?: string;
  status?: string;
  limit?: number;
}): Promise<{ signals: Signal[] }> {
  const query = new URLSearchParams();
  if (params?.inst_id) query.set("inst_id", params.inst_id);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiFetch(`/api/signals${qs ? `?${qs}` : ""}`);
}

export async function confirmSignal(signalId: number, leverage = 3) {
  return apiFetch(`/api/signals/${signalId}/confirm`, {
    method: "POST",
    body: JSON.stringify({ leverage, margin_mode: "isolated" }),
  });
}

export async function skipSignal(signalId: number) {
  return apiFetch(`/api/signals/${signalId}/skip`, {
    method: "POST",
  });
}

// 持仓
export async function getPositions(flag?: string) {
  const qs = flag ? `?flag=${flag}` : "";
  return apiFetch(`/api/positions${qs}`);
}

export async function getBalance(flag?: string) {
  return apiFetch(`/api/positions/balance${flag ? `?flag=${flag}` : ""}`);
}

export async function getTrades(params?: { inst_id?: string; limit?: number }) {
  const query = new URLSearchParams();
  if (params?.inst_id) query.set("inst_id", params.inst_id);
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiFetch(`/api/positions/trades${qs ? `?${qs}` : ""}`);
}

export async function closePosition(instId: string, flag?: string) {
  return apiFetch(`/api/positions/${encodeURIComponent(instId)}/close`, {
    method: "POST",
    body: JSON.stringify({ flag }),
  });
}

// 交易记录（独立路由）
export async function getTradeRecords(params?: { inst_id?: string; limit?: number }) {
  const query = new URLSearchParams();
  if (params?.inst_id) query.set("inst_id", params.inst_id);
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiFetch(`/api/trades${qs ? `?${qs}` : ""}`);
}

export async function getTradeSummary() {
  return apiFetch("/api/trades/summary");
}

export async function getTradingMode() {
  return apiFetch<{ flag: string; mode: string }>("/api/signals/trading/mode");
}

// WebSocket 连接（含自动重连 + 指数退避）
export function connectSignalsWS(onMessage: (data: unknown) => void): { close: () => void } {
  if (typeof window === "undefined") return { close: () => {} };

  const token = getToken();
  const wsUrl = API_BASE.replace("http", "ws");
  let ws: WebSocket | null = null;
  let retryCount = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  function connect() {
    if (closed) return;
    const url = `${wsUrl}/api/signals/ws/signals${token ? `?token=${token}` : ""}`;
    ws = new WebSocket(url);

    ws.onopen = () => {
      retryCount = 0;  // 连接成功重置计数
    };

    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch (err) {
        console.warn("WebSocket 消息解析失败:", err);
      }
    };

    ws.onclose = () => {
      if (closed) return;
      // 指数退避重连：1s, 2s, 4s, 8s, 16s, 最大 30s
      const delay = Math.min(1000 * Math.pow(2, retryCount), 30000);
      retryCount++;
      retryTimer = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose 会在 onerror 后触发，由 onclose 处理重连
    };
  }

  connect();

  return {
    close: () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    },
  };
}
