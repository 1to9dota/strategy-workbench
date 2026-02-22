"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { isLoggedIn, runBacktest, getBacktestHistory, getCandles, logout } from "@/lib/api";
import type { BacktestResult, BacktestHistory, Candle } from "@/lib/types";
import CandlestickChart from "@/components/CandlestickChart";
import EquityCurve from "@/components/EquityCurve";
import BacktestReport from "@/components/BacktestReport";

const STRATEGIES = [
  { id: "macd_divergence", name: "MACD背离" },
  { id: "pin_bar", name: "针形态" },
  { id: "ma90", name: "MA90突破" },
];

const PAIRS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"];
const BARS = ["1H", "4H", "1D"];

export default function BacktestPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 表单状态
  const [instId, setInstId] = useState("BTC-USDT-SWAP");
  const [bar, setBar] = useState("4H");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2025-01-01");
  const [selectedStrategies, setSelectedStrategies] = useState(["macd_divergence", "pin_bar", "ma90"]);
  const [minStrength, setMinStrength] = useState(1);
  const [initialCapital, setInitialCapital] = useState(10000);

  // 结果状态
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [history, setHistory] = useState<BacktestHistory[]>([]);
  const [activeTab, setActiveTab] = useState<"form" | "result">("form");

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    getBacktestHistory().then(setHistory).catch((e) => console.warn("加载回测历史失败:", e));
  }, [router]);

  const handleRun = async () => {
    if (selectedStrategies.length === 0) {
      setError("请至少选择一个策略");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await runBacktest({
        inst_id: instId,
        bar,
        start_date: startDate,
        end_date: endDate,
        strategies: selectedStrategies,
        min_strength: minStrength,
        initial_capital: initialCapital,
      });

      if ("error" in res) {
        setError((res as { error: string }).error);
        return;
      }

      setResult(res);
      setActiveTab("result");

      // 拉取K线用于图表展示
      const candleRes = await getCandles(instId, bar, 3000);
      // 过滤到回测时间范围
      const startTs = new Date(startDate).getTime();
      const endTs = new Date(endDate).getTime();
      const filtered = candleRes.data.filter(
        (c: Candle) => c.ts >= startTs && c.ts <= endTs
      );
      setCandles(filtered);

      // 刷新历史
      getBacktestHistory().then(setHistory).catch((e) => console.warn("加载回测历史失败:", e));
    } catch (e) {
      setError(e instanceof Error ? e.message : "回测失败");
    } finally {
      setLoading(false);
    }
  };

  const toggleStrategy = (id: string) => {
    setSelectedStrategies((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  };

  return (
    <div className="min-h-screen bg-[#0a0b0f] text-white">
      {/* 顶部导航 */}
      <nav className="border-b border-gray-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <h1 className="font-bold text-lg">策略工作台</h1>
          <a href="/backtest" className="text-blue-400 text-sm">回测中心</a>
        </div>
        <button onClick={logout} className="text-gray-500 hover:text-gray-300 text-sm">
          退出
        </button>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* 标签切换 */}
        <div className="flex gap-4 mb-6">
          <button
            onClick={() => setActiveTab("form")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === "form" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            参数配置
          </button>
          {result && (
            <button
              onClick={() => setActiveTab("result")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === "result" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              回测结果
            </button>
          )}
        </div>

        {activeTab === "form" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* 参数表单 */}
            <div className="lg:col-span-2 bg-gray-900 rounded-xl p-6 space-y-5">
              <h2 className="text-lg font-medium">回测参数</h2>

              {error && (
                <div className="bg-red-900/30 text-red-400 text-sm rounded-lg p-3">{error}</div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">交易对</label>
                  <select
                    value={instId}
                    onChange={(e) => setInstId(e.target.value)}
                    className="w-full bg-gray-800 rounded-lg px-4 py-2.5 text-white outline-none"
                  >
                    {PAIRS.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">K线周期</label>
                  <select
                    value={bar}
                    onChange={(e) => setBar(e.target.value)}
                    className="w-full bg-gray-800 rounded-lg px-4 py-2.5 text-white outline-none"
                  >
                    {BARS.map((b) => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">开始日期</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full bg-gray-800 rounded-lg px-4 py-2.5 text-white outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">结束日期</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full bg-gray-800 rounded-lg px-4 py-2.5 text-white outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">策略选择</label>
                <div className="flex gap-3">
                  {STRATEGIES.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => toggleStrategy(s.id)}
                      className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                        selectedStrategies.includes(s.id)
                          ? "bg-blue-600 text-white"
                          : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                      }`}
                    >
                      {s.name}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">最低信号强度</label>
                  <select
                    value={minStrength}
                    onChange={(e) => setMinStrength(Number(e.target.value))}
                    className="w-full bg-gray-800 rounded-lg px-4 py-2.5 text-white outline-none"
                  >
                    <option value={1}>1 (单策略即触发)</option>
                    <option value={2}>2 (双策略共振)</option>
                    <option value={3}>3 (三策略共振)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">初始资金 (USDT)</label>
                  <input
                    type="number"
                    value={initialCapital}
                    onChange={(e) => setInitialCapital(Number(e.target.value))}
                    className="w-full bg-gray-800 rounded-lg px-4 py-2.5 text-white outline-none"
                  />
                </div>
              </div>

              <button
                onClick={handleRun}
                disabled={loading}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white rounded-lg py-3 font-medium transition-colors flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <span className="animate-spin">&#9696;</span>
                    回测中...
                  </>
                ) : (
                  "开始回测"
                )}
              </button>
            </div>

            {/* 历史记录 */}
            <div className="bg-gray-900 rounded-xl p-6">
              <h2 className="text-lg font-medium mb-4">回测历史</h2>
              {history.length === 0 ? (
                <p className="text-gray-500 text-sm">暂无记录</p>
              ) : (
                <div className="space-y-3">
                  {history.map((h) => (
                    <div
                      key={h.id}
                      className="bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800 transition-colors cursor-pointer"
                    >
                      <div className="flex justify-between items-start">
                        <div className="text-sm font-medium truncate">{h.name}</div>
                        <span
                          className={`text-sm font-mono ${
                            h.result.total_return_pct >= 0 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {h.result.total_return_pct > 0 ? "+" : ""}
                          {h.result.total_return_pct.toFixed(1)}%
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {h.result.total_trades}笔 | 胜率 {h.result.win_rate.toFixed(0)}% |
                        回撤 {h.result.max_drawdown_pct.toFixed(1)}%
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "result" && result && (
          <div className="space-y-6">
            {/* K线图 + 信号标注 */}
            <div className="bg-gray-900 rounded-xl p-6">
              <h2 className="text-lg font-medium mb-4">K线图 + 信号标注</h2>
              {candles.length > 0 ? (
                <CandlestickChart
                  candles={candles}
                  trades={result.trades}
                  height={500}
                />
              ) : (
                <div className="h-[500px] flex items-center justify-center text-gray-500">
                  K线数据加载中...
                </div>
              )}
            </div>

            {/* 资金曲线 */}
            <div className="bg-gray-900 rounded-xl p-6">
              <h2 className="text-lg font-medium mb-4">资金曲线</h2>
              <EquityCurve
                data={result.equity_curve}
                initialCapital={result.report.initial_capital}
                height={280}
              />
            </div>

            {/* 回测报告 */}
            <div className="bg-gray-900 rounded-xl p-6">
              <h2 className="text-lg font-medium mb-4">回测报告</h2>
              <BacktestReport report={result.report} trades={result.trades} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
