"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSignals, getBalance, getPositions, getTradeSummary, getTradingMode, isLoggedIn } from "@/lib/api";
import type { Signal, OKXPosition, TradeStats } from "@/lib/types";

export default function Dashboard() {
  const router = useRouter();
  const [totalEq, setTotalEq] = useState("0");
  const [mode, setMode] = useState("模拟盘");
  const [positions, setPositions] = useState<OKXPosition[]>([]);
  const [recentSignals, setRecentSignals] = useState<Signal[]>([]);
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    (async () => {
      try {
        const [balData, posData, sigData, summaryData, modeData] = await Promise.all([
          getBalance() as Promise<{ balance: Record<string, unknown> }>,
          getPositions() as Promise<{ positions: OKXPosition[] }>,
          getSignals({ limit: 5 }) as Promise<{ signals: Signal[] }>,
          getTradeSummary() as Promise<{ total: TradeStats }>,
          getTradingMode(),
        ]);
        setTotalEq((balData.balance as Record<string, string>)?.totalEq || "0");
        setPositions(posData.positions.filter((p) => parseFloat(p.pos) !== 0));
        setRecentSignals(sigData.signals);
        setStats(summaryData.total);
        setMode(modeData.mode);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  if (loading) {
    return <div className="min-h-screen bg-[#0a0b0f] flex items-center justify-center text-gray-500">加载中...</div>;
  }

  const pendingSignals = recentSignals.filter((s) => s.status === "pending").length;

  return (
    <div className="min-h-screen bg-[#0a0b0f] p-6">
      {/* 顶部 */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">策略工作台</h1>
          <span className={`text-xs px-2 py-0.5 rounded ${
            mode === "模拟盘" ? "bg-blue-800/30 text-blue-400" : "bg-red-800/30 text-red-400"
          }`}>{mode}</span>
        </div>
        <nav className="flex gap-3">
          <NavLink href="/backtest">回测</NavLink>
          <NavLink href="/signals">信号</NavLink>
          <NavLink href="/positions">持仓</NavLink>
          <NavLink href="/trades">交易</NavLink>
          <NavLink href="/settings">配置</NavLink>
        </nav>
      </div>

      {/* 核心指标 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <BigCard label="账户权益" value={`${parseFloat(totalEq).toFixed(2)}`} unit="USDT" />
        <BigCard label="活跃持仓" value={String(positions.length)} onClick={() => router.push("/positions")} />
        <BigCard label="待处理信号" value={String(pendingSignals)}
                 color={pendingSignals > 0 ? "yellow" : undefined}
                 onClick={() => router.push("/signals")} />
        <BigCard label="总盈亏" value={stats ? `${stats.total_pnl >= 0 ? "+" : ""}${stats.total_pnl.toFixed(2)}` : "0"}
                 color={stats && stats.total_pnl >= 0 ? "green" : "red"}
                 onClick={() => router.push("/trades")} />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* 交易统计 */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
          <h2 className="text-white font-semibold mb-4">交易统计</h2>
          {stats && stats.count > 0 ? (
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><span className="text-gray-400">总交易</span> <span className="text-white ml-2">{stats.count}</span></div>
              <div><span className="text-gray-400">胜率</span>
                <span className={`ml-2 ${stats.win_rate >= 50 ? "text-green-400" : "text-red-400"}`}>{stats.win_rate}%</span>
              </div>
              <div><span className="text-gray-400">胜 / 负</span>
                <span className="ml-2 text-green-400">{stats.wins}</span>
                <span className="text-gray-500"> / </span>
                <span className="text-red-400">{stats.count - stats.wins}</span>
              </div>
              <div><span className="text-gray-400">盈亏比</span>
                <span className="text-white ml-2">
                  {stats.profit_factor === Infinity ? "∞" : stats.profit_factor.toFixed(2)}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">暂无已平仓交易</p>
          )}
        </div>

        {/* 当前持仓 */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">当前持仓</h2>
            <a href="/positions" className="text-xs text-blue-400 hover:text-blue-300">查看全部</a>
          </div>
          {positions.length === 0 ? (
            <p className="text-gray-500 text-sm">暂无持仓</p>
          ) : (
            <div className="space-y-2">
              {positions.map((p) => {
                const upl = parseFloat(p.upl || "0");
                return (
                  <div key={p.instId} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-white">{p.instId}</span>
                      <span className={`text-xs ${parseFloat(p.pos) > 0 ? "text-green-400" : "text-red-400"}`}>
                        {parseFloat(p.pos) > 0 ? "LONG" : "SHORT"}
                      </span>
                      <span className="text-gray-500">{p.lever}x</span>
                    </div>
                    <span className={upl >= 0 ? "text-green-400" : "text-red-400"}>
                      {upl >= 0 ? "+" : ""}{upl.toFixed(2)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 最近信号 */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5 md:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">最近信号</h2>
            <a href="/signals" className="text-xs text-blue-400 hover:text-blue-300">查看全部</a>
          </div>
          {recentSignals.length === 0 ? (
            <p className="text-gray-500 text-sm">暂无信号，扫描引擎每分钟自动检查</p>
          ) : (
            <div className="space-y-2">
              {recentSignals.map((s) => (
                <div key={s.id} className="flex items-center justify-between text-sm py-1 border-b border-gray-800/50">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                      s.direction === "long" ? "bg-green-800/30 text-green-400" : "bg-red-800/30 text-red-400"
                    }`}>
                      {s.direction.toUpperCase()}
                    </span>
                    <span className="text-white">{s.inst_id}</span>
                    <span className="text-gray-500">{s.bar}</span>
                    <span className="text-yellow-400 text-xs">{"★".repeat(s.strength)}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      s.status === "pending" ? "bg-yellow-800/30 text-yellow-400" :
                      s.status === "confirmed" ? "bg-green-800/30 text-green-400" :
                      "bg-gray-700/30 text-gray-400"
                    }`}>
                      {s.status === "pending" ? "待处理" : s.status === "confirmed" ? "已确认" :
                       s.status === "skipped" ? "已跳过" : s.status}
                    </span>
                    <span className="text-gray-500 text-xs">
                      {new Date(s.created_at).toLocaleString("zh-CN")}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} className="text-sm text-gray-400 hover:text-white px-3 py-1.5 rounded hover:bg-gray-800">
      {children}
    </a>
  );
}

function BigCard({ label, value, unit, color, onClick }: {
  label: string; value: string; unit?: string; color?: string;
  onClick?: () => void;
}) {
  const textColor = color === "green" ? "text-green-400" : color === "red" ? "text-red-400" :
    color === "yellow" ? "text-yellow-400" : "text-white";
  return (
    <div onClick={onClick}
         className={`bg-gray-900/50 border border-gray-800 rounded-lg p-4 ${onClick ? "cursor-pointer hover:border-gray-600" : ""}`}>
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${textColor}`}>
        {value}
        {unit && <span className="text-sm text-gray-500 ml-1">{unit}</span>}
      </div>
    </div>
  );
}
