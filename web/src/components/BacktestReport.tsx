"use client";

import type { BacktestReport as ReportType, BacktestTrade } from "@/lib/types";

interface Props {
  report: ReportType;
  trades: BacktestTrade[];
}

export default function BacktestReport({ report, trades }: Props) {
  return (
    <div className="space-y-6">
      {/* 核心指标网格 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="总收益率"
          value={`${report.total_return_pct > 0 ? "+" : ""}${report.total_return_pct.toFixed(2)}%`}
          color={report.total_return_pct >= 0 ? "text-green-400" : "text-red-400"}
        />
        <MetricCard
          label="胜率"
          value={`${report.win_rate.toFixed(1)}%`}
          sub={`${report.winning_trades}/${report.total_trades}`}
        />
        <MetricCard
          label="盈亏比"
          value={report.profit_factor === Infinity ? "∞" : report.profit_factor.toFixed(2)}
          color={report.profit_factor >= 1.5 ? "text-green-400" : report.profit_factor >= 1 ? "text-yellow-400" : "text-red-400"}
        />
        <MetricCard
          label="最大回撤"
          value={`-${report.max_drawdown_pct.toFixed(2)}%`}
          color="text-red-400"
        />
        <MetricCard
          label="Sharpe"
          value={report.sharpe_ratio.toFixed(2)}
          color={report.sharpe_ratio > 1 ? "text-green-400" : "text-gray-400"}
        />
        <MetricCard
          label="最终资金"
          value={`$${report.final_capital.toLocaleString()}`}
        />
        <MetricCard
          label="平均盈利"
          value={`+${report.avg_win_pct.toFixed(2)}%`}
          color="text-green-400"
        />
        <MetricCard
          label="平均亏损"
          value={`${report.avg_loss_pct.toFixed(2)}%`}
          color="text-red-400"
        />
      </div>

      {/* Buy & Hold 对比 */}
      <div className="bg-gray-800/50 rounded-lg p-4 flex items-center justify-between">
        <span className="text-gray-400">Buy &amp; Hold 对比</span>
        <div className="flex gap-6">
          <span>
            策略:{" "}
            <span className={report.total_return_pct >= 0 ? "text-green-400" : "text-red-400"}>
              {report.total_return_pct > 0 ? "+" : ""}{report.total_return_pct.toFixed(2)}%
            </span>
          </span>
          <span>
            持有:{" "}
            <span className={report.buy_hold_return_pct >= 0 ? "text-green-400" : "text-red-400"}>
              {report.buy_hold_return_pct > 0 ? "+" : ""}{report.buy_hold_return_pct.toFixed(2)}%
            </span>
          </span>
        </div>
      </div>

      {/* 标签统计 */}
      {report.tag_stats && Object.keys(report.tag_stats).length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-400 mb-3">信号标签统计</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {Object.entries(report.tag_stats).map(([tag, stats]) => (
              <div key={tag} className="bg-gray-800/50 rounded-lg p-3 flex items-center justify-between">
                <span className="text-sm font-mono text-blue-400">{tag}</span>
                <div className="flex gap-3 text-sm">
                  <span>{stats.count}笔</span>
                  <span>胜率 {stats.count > 0 ? ((stats.wins / stats.count) * 100).toFixed(0) : 0}%</span>
                  <span className={stats.total_pnl >= 0 ? "text-green-400" : "text-red-400"}>
                    ${stats.total_pnl.toFixed(0)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 交易明细表格 */}
      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-3">
          交易明细 ({trades.length}笔)
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-gray-700">
                <th className="py-2 px-3 text-left">#</th>
                <th className="py-2 px-3 text-left">方向</th>
                <th className="py-2 px-3 text-right">入场价</th>
                <th className="py-2 px-3 text-right">出场价</th>
                <th className="py-2 px-3 text-right">盈亏</th>
                <th className="py-2 px-3 text-right">盈亏%</th>
                <th className="py-2 px-3 text-left">出场原因</th>
                <th className="py-2 px-3 text-left">标签</th>
                <th className="py-2 px-3 text-center">强度</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => (
                <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/30">
                  <td className="py-2 px-3 text-gray-500">{i + 1}</td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      t.direction === "long" ? "bg-green-900/50 text-green-400" : "bg-red-900/50 text-red-400"
                    }`}>
                      {t.direction === "long" ? "做多" : "做空"}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right font-mono">{t.entry_price.toFixed(2)}</td>
                  <td className="py-2 px-3 text-right font-mono">{t.exit_price.toFixed(2)}</td>
                  <td className={`py-2 px-3 text-right font-mono ${t.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(2)}
                  </td>
                  <td className={`py-2 px-3 text-right font-mono ${t.pnl_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct.toFixed(2)}%
                  </td>
                  <td className="py-2 px-3 text-gray-400 text-xs">{t.exit_reason}</td>
                  <td className="py-2 px-3 font-mono text-xs text-blue-400">{t.enter_tag}</td>
                  <td className="py-2 px-3 text-center">
                    {"⬤".repeat(t.strength)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  sub,
  color = "text-white",
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-gray-800/50 rounded-lg p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}
