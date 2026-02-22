"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { getSignals, confirmSignal, skipSignal, connectSignalsWS, isLoggedIn } from "@/lib/api";
import SignalCard from "@/components/SignalCard";
import type { Signal } from "@/lib/types";

type FilterStatus = "all" | "pending" | "confirmed" | "skipped";

export default function SignalsPage() {
  const router = useRouter();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterStatus>("all");

  const loadSignals = useCallback(async () => {
    try {
      const params: { status?: string; limit?: number } = { limit: 100 };
      if (filter !== "all") params.status = filter;
      const data = await getSignals(params);
      setSignals(data.signals);
    } catch (e) {
      console.error("加载信号失败:", e);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    loadSignals();
  }, [router, loadSignals]);

  // WebSocket 实时推送（含自动重连）
  useEffect(() => {
    const conn = connectSignalsWS((data: unknown) => {
      const msg = data as { type: string; signal?: Signal; signal_id?: number; status?: string };
      if (msg.type === "new_signal" && msg.signal) {
        setSignals((prev) => [msg.signal!, ...prev]);
      } else if (msg.type === "signal_status" && msg.signal_id) {
        setSignals((prev) =>
          prev.map((s) =>
            s.id === msg.signal_id ? { ...s, status: msg.status as Signal["status"] } : s
          )
        );
      }
    });
    return () => {
      conn.close();
    };
  }, []);

  const handleConfirm = async (id: number) => {
    try {
      await confirmSignal(id);
      setSignals((prev) =>
        prev.map((s) => (s.id === id ? { ...s, status: "confirmed" } : s))
      );
    } catch (e) {
      alert("确认失败: " + (e as Error).message);
    }
  };

  const handleSkip = async (id: number) => {
    try {
      await skipSignal(id);
      setSignals((prev) =>
        prev.map((s) => (s.id === id ? { ...s, status: "skipped" } : s))
      );
    } catch (e) {
      alert("跳过失败: " + (e as Error).message);
    }
  };

  const pendingCount = signals.filter((s) => s.status === "pending").length;

  return (
    <div className="min-h-screen bg-[#0a0b0f] p-6">
      {/* 顶部导航 */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold text-white">信号监控</h1>
          {pendingCount > 0 && (
            <span className="bg-yellow-600/30 text-yellow-400 text-sm px-2 py-0.5 rounded">
              {pendingCount} 待处理
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <a href="/backtest" className="text-sm text-gray-400 hover:text-white px-3 py-1">
            回测中心
          </a>
          <button
            onClick={loadSignals}
            className="text-sm bg-gray-700 hover:bg-gray-600 text-white px-3 py-1 rounded cursor-pointer"
          >
            刷新
          </button>
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="flex gap-2 mb-6">
        {(["all", "pending", "confirmed", "skipped"] as FilterStatus[]).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1 text-sm rounded cursor-pointer ${
              filter === s
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {s === "all" ? "全部" : s === "pending" ? "待处理" : s === "confirmed" ? "已确认" : "已跳过"}
          </button>
        ))}
      </div>

      {/* 信号列表 */}
      {loading ? (
        <div className="text-center text-gray-500 py-20">加载中...</div>
      ) : signals.length === 0 ? (
        <div className="text-center text-gray-500 py-20">
          <p className="text-lg mb-2">暂无信号</p>
          <p className="text-sm">扫描引擎每分钟检查一次，发现信号会实时推送到这里</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {signals.map((signal) => (
            <SignalCard
              key={signal.id}
              signal={signal}
              onConfirm={handleConfirm}
              onSkip={handleSkip}
            />
          ))}
        </div>
      )}
    </div>
  );
}
