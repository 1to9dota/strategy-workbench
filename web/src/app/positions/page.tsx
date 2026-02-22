"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getPositions, getBalance, getTrades, closePosition, getTradingMode, isLoggedIn } from "@/lib/api";
import type { OKXPosition, TradeRecord } from "@/lib/types";

export default function PositionsPage() {
  const router = useRouter();
  const [positions, setPositions] = useState<OKXPosition[]>([]);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [balance, setBalance] = useState<Record<string, string>>({});
  const [mode, setMode] = useState("模拟盘");
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [posData, balData, tradeData, modeData] = await Promise.all([
        getPositions() as Promise<{ positions: OKXPosition[]; mode: string }>,
        getBalance() as Promise<{ balance: Record<string, unknown> }>,
        getTrades({ limit: 20 }) as Promise<{ trades: TradeRecord[] }>,
        getTradingMode(),
      ]);
      setPositions(posData.positions.filter((p: OKXPosition) => parseFloat(p.pos) !== 0));
      setBalance(balData.balance as Record<string, string>);
      setTrades(tradeData.trades);
      setMode(modeData.mode);
    } catch (e) {
      console.error("加载数据失败:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    loadData();
  }, [router]);

  const handleClose = async (instId: string) => {
    if (!confirm(`确认平仓 ${instId}？`)) return;
    setClosing(instId);
    try {
      await closePosition(instId);
      await loadData();
    } catch (e) {
      alert("平仓失败: " + (e as Error).message);
    } finally {
      setClosing(null);
    }
  };

  const totalEq = balance?.totalEq || "0";

  return (
    <div className="min-h-screen bg-[#0a0b0f] p-6">
      {/* 顶部导航 */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white">仓位管理</h1>
          <span className={`text-xs px-2 py-0.5 rounded ${
            mode === "模拟盘" ? "bg-blue-800/30 text-blue-400" : "bg-red-800/30 text-red-400"
          }`}>
            {mode}
          </span>
        </div>
        <div className="flex gap-2">
          <a href="/signals" className="text-sm text-gray-400 hover:text-white px-3 py-1">信号监控</a>
          <a href="/backtest" className="text-sm text-gray-400 hover:text-white px-3 py-1">回测中心</a>
          <button onClick={loadData} className="text-sm bg-gray-700 hover:bg-gray-600 text-white px-3 py-1 rounded cursor-pointer">
            刷新
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-gray-500 py-20">加载中...</div>
      ) : (
        <>
          {/* 账户概览 */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4 mb-6">
            <h2 className="text-sm text-gray-400 mb-2">账户权益</h2>
            <p className="text-3xl font-bold text-white font-mono">
              {parseFloat(totalEq).toFixed(2)} <span className="text-sm text-gray-400">USDT</span>
            </p>
          </div>

          {/* 当前持仓 */}
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-white mb-3">
              当前持仓 ({positions.length})
            </h2>
            {positions.length === 0 ? (
              <div className="text-center text-gray-500 py-10 border border-gray-800 rounded-lg">
                暂无持仓
              </div>
            ) : (
              <div className="grid gap-3">
                {positions.map((p) => {
                  const upl = parseFloat(p.upl || "0");
                  const uplRatio = parseFloat(p.uplRatio || "0") * 100;
                  const isProfit = upl >= 0;
                  return (
                    <div key={p.instId + p.posSide}
                         className="bg-gray-900/50 border border-gray-800 rounded-lg p-4 flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold text-white">{p.instId}</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            parseFloat(p.pos) > 0 ? "bg-green-800/30 text-green-400" : "bg-red-800/30 text-red-400"
                          }`}>
                            {parseFloat(p.pos) > 0 ? "LONG" : "SHORT"}
                          </span>
                          <span className="text-xs text-gray-500">{p.lever}x {p.mgnMode}</span>
                        </div>
                        <div className="flex gap-4 text-sm">
                          <span className="text-gray-400">均价 <span className="text-white font-mono">{parseFloat(p.avgPx).toFixed(2)}</span></span>
                          <span className="text-gray-400">保证金 <span className="text-white font-mono">{parseFloat(p.margin).toFixed(2)}</span></span>
                          <span className={isProfit ? "text-green-400" : "text-red-400"}>
                            {isProfit ? "+" : ""}{upl.toFixed(2)} ({isProfit ? "+" : ""}{uplRatio.toFixed(2)}%)
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={() => handleClose(p.instId)}
                        disabled={closing === p.instId}
                        className="px-4 py-2 bg-red-600 hover:bg-red-500 disabled:bg-gray-600 text-white text-sm rounded cursor-pointer"
                      >
                        {closing === p.instId ? "平仓中..." : "平仓"}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 最近交易 */}
          <div>
            <h2 className="text-lg font-semibold text-white mb-3">最近交易</h2>
            {trades.length === 0 ? (
              <div className="text-center text-gray-500 py-10 border border-gray-800 rounded-lg">
                暂无交易记录
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-800">
                      <th className="text-left py-2 px-3">币种</th>
                      <th className="text-left py-2 px-3">方向</th>
                      <th className="text-right py-2 px-3">入场价</th>
                      <th className="text-right py-2 px-3">出场价</th>
                      <th className="text-right py-2 px-3">盈亏</th>
                      <th className="text-right py-2 px-3">金额</th>
                      <th className="text-left py-2 px-3">原因</th>
                      <th className="text-left py-2 px-3">时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t) => (
                      <tr key={t.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                        <td className="py-2 px-3 text-white">{t.inst_id}</td>
                        <td className="py-2 px-3">
                          <span className={t.direction === "long" ? "text-green-400" : "text-red-400"}>
                            {t.direction.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-right font-mono text-white">{t.entry_price.toFixed(2)}</td>
                        <td className="py-2 px-3 text-right font-mono text-white">
                          {t.exit_price ? t.exit_price.toFixed(2) : "-"}
                        </td>
                        <td className={`py-2 px-3 text-right font-mono ${
                          t.pnl === null ? "text-gray-400" : t.pnl >= 0 ? "text-green-400" : "text-red-400"
                        }`}>
                          {t.pnl !== null ? `${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}` : "持仓中"}
                        </td>
                        <td className="py-2 px-3 text-right font-mono text-gray-300">{t.position_size.toFixed(0)}</td>
                        <td className="py-2 px-3 text-gray-400">{t.exit_reason || "-"}</td>
                        <td className="py-2 px-3 text-gray-500 text-xs">
                          {new Date(t.created_at).toLocaleString("zh-CN")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
