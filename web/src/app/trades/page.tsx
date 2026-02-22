"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getTradeRecords, getTradeSummary, isLoggedIn } from "@/lib/api";
import type { TradeRecord, TradeStats } from "@/lib/types";

interface Summary {
  total: TradeStats;
  weekly: TradeStats[];
  monthly: TradeStats[];
  by_strategy: Record<string, TradeStats>;
}

export default function TradesPage() {
  const router = useRouter();
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"trades" | "weekly" | "monthly" | "strategy">("trades");

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    (async () => {
      try {
        const [tradeData, summaryData] = await Promise.all([
          getTradeRecords({ limit: 200 }) as Promise<{ trades: TradeRecord[] }>,
          getTradeSummary() as Promise<Summary>,
        ]);
        setTrades(tradeData.trades);
        setSummary(summaryData);
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

  const total = summary?.total;

  return (
    <div className="min-h-screen bg-[#0a0b0f] p-6">
      {/* 导航 */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">交易记录</h1>
        <div className="flex gap-2">
          <a href="/" className="text-sm text-gray-400 hover:text-white px-3 py-1">Dashboard</a>
          <a href="/signals" className="text-sm text-gray-400 hover:text-white px-3 py-1">信号</a>
          <a href="/positions" className="text-sm text-gray-400 hover:text-white px-3 py-1">持仓</a>
        </div>
      </div>

      {/* 总体统计卡片 */}
      {total && total.count > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          <StatCard label="总交易" value={total.count} />
          <StatCard label="胜率" value={`${total.win_rate}%`} color={total.win_rate >= 50 ? "green" : "red"} />
          <StatCard label="总盈亏" value={`${total.total_pnl >= 0 ? "+" : ""}${total.total_pnl.toFixed(2)}`}
                    color={total.total_pnl >= 0 ? "green" : "red"} />
          <StatCard label="盈亏比" value={total.profit_factor === Infinity ? "∞" : total.profit_factor.toFixed(2)} />
          <StatCard label="平均盈亏" value={`${total.avg_pnl >= 0 ? "+" : ""}${total.avg_pnl.toFixed(2)}`}
                    color={total.avg_pnl >= 0 ? "green" : "red"} />
        </div>
      )}

      {/* Tab 切换 */}
      <div className="flex gap-2 mb-4">
        {(["trades", "weekly", "monthly", "strategy"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1 text-sm rounded cursor-pointer ${
              tab === t ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}>
            {t === "trades" ? "明细" : t === "weekly" ? "按周" : t === "monthly" ? "按月" : "按策略"}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      {tab === "trades" && <TradeTable trades={trades} />}
      {tab === "weekly" && <PeriodTable data={summary?.weekly || []} label="周" />}
      {tab === "monthly" && <PeriodTable data={summary?.monthly || []} label="月" />}
      {tab === "strategy" && <StrategyTable data={summary?.by_strategy || {}} />}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  const textColor = color === "green" ? "text-green-400" : color === "red" ? "text-red-400" : "text-white";
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-3">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className={`text-lg font-bold font-mono ${textColor}`}>{value}</div>
    </div>
  );
}

function TradeTable({ trades }: { trades: TradeRecord[] }) {
  if (!trades.length) return <div className="text-center text-gray-500 py-10">暂无交易记录</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-400 border-b border-gray-800">
            <th className="text-left py-2 px-3">#</th>
            <th className="text-left py-2 px-3">币种</th>
            <th className="text-left py-2 px-3">方向</th>
            <th className="text-right py-2 px-3">入场价</th>
            <th className="text-right py-2 px-3">出场价</th>
            <th className="text-right py-2 px-3">盈亏</th>
            <th className="text-right py-2 px-3">盈亏%</th>
            <th className="text-right py-2 px-3">金额</th>
            <th className="text-left py-2 px-3">杠杆</th>
            <th className="text-left py-2 px-3">原因</th>
            <th className="text-left py-2 px-3">时间</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
              <td className="py-2 px-3 text-gray-500">{t.id}</td>
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
              <td className={`py-2 px-3 text-right font-mono ${
                t.pnl_pct === null ? "text-gray-400" : t.pnl_pct >= 0 ? "text-green-400" : "text-red-400"
              }`}>
                {t.pnl_pct !== null ? `${t.pnl_pct >= 0 ? "+" : ""}${t.pnl_pct.toFixed(2)}%` : "-"}
              </td>
              <td className="py-2 px-3 text-right font-mono text-gray-300">{t.position_size.toFixed(0)}</td>
              <td className="py-2 px-3 text-gray-400">{t.leverage}x</td>
              <td className="py-2 px-3 text-gray-400">{t.exit_reason || "-"}</td>
              <td className="py-2 px-3 text-gray-500 text-xs">
                {new Date(t.created_at).toLocaleString("zh-CN")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PeriodTable({ data, label }: { data: TradeStats[]; label: string }) {
  if (!data.length) return <div className="text-center text-gray-500 py-10">暂无数据</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-400 border-b border-gray-800">
            <th className="text-left py-2 px-3">{label}</th>
            <th className="text-right py-2 px-3">交易数</th>
            <th className="text-right py-2 px-3">胜率</th>
            <th className="text-right py-2 px-3">总盈亏</th>
            <th className="text-right py-2 px-3">平均</th>
            <th className="text-right py-2 px-3">最佳</th>
            <th className="text-right py-2 px-3">最差</th>
            <th className="text-right py-2 px-3">盈亏比</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.period} className="border-b border-gray-800/50 hover:bg-gray-800/30">
              <td className="py-2 px-3 text-white font-mono">{d.period}</td>
              <td className="py-2 px-3 text-right text-gray-300">{d.count}</td>
              <td className={`py-2 px-3 text-right ${d.win_rate >= 50 ? "text-green-400" : "text-red-400"}`}>
                {d.win_rate}%
              </td>
              <td className={`py-2 px-3 text-right font-mono ${d.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                {d.total_pnl >= 0 ? "+" : ""}{d.total_pnl.toFixed(2)}
              </td>
              <td className="py-2 px-3 text-right font-mono text-gray-300">{d.avg_pnl.toFixed(2)}</td>
              <td className="py-2 px-3 text-right font-mono text-green-400">+{d.best.toFixed(2)}</td>
              <td className="py-2 px-3 text-right font-mono text-red-400">{d.worst.toFixed(2)}</td>
              <td className="py-2 px-3 text-right text-gray-300">
                {d.profit_factor === Infinity ? "∞" : d.profit_factor.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StrategyTable({ data }: { data: Record<string, TradeStats> }) {
  const entries = Object.entries(data);
  if (!entries.length) return <div className="text-center text-gray-500 py-10">暂无策略统计</div>;
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {entries.map(([name, s]) => (
        <div key={name} className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-2">{name}</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div><span className="text-gray-400">交易数</span> <span className="text-white">{s.count}</span></div>
            <div><span className="text-gray-400">胜率</span>
              <span className={s.win_rate >= 50 ? "text-green-400" : "text-red-400"}> {s.win_rate}%</span>
            </div>
            <div><span className="text-gray-400">总盈亏</span>
              <span className={s.total_pnl >= 0 ? "text-green-400" : "text-red-400"}>
                {" "}{s.total_pnl >= 0 ? "+" : ""}{s.total_pnl.toFixed(2)}
              </span>
            </div>
            <div><span className="text-gray-400">盈亏比</span>
              <span className="text-white"> {s.profit_factor === Infinity ? "∞" : s.profit_factor.toFixed(2)}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
