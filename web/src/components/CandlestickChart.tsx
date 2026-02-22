"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  ColorType,
  type CandlestickData,
  type Time,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
} from "lightweight-charts";
import type { Candle, BacktestTrade, BacktestSignal } from "@/lib/types";

interface Props {
  candles: Candle[];
  trades?: BacktestTrade[];
  signals?: BacktestSignal[];
  height?: number;
}

export default function CandlestickChart({
  candles,
  trades,
  signals,
  height = 500,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    // 清理旧图表
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#0f1117" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      crosshair: {
        mode: 0,
      },
      timeScale: {
        borderColor: "#374151",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "#374151",
      },
    });

    chartRef.current = chart;

    // K线数据（v5 API: chart.addSeries）
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    const chartData: CandlestickData<Time>[] = candles.map((c) => ({
      time: (c.ts / 1000) as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    candleSeries.setData(chartData);

    // 成交量
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    volumeSeries.setData(
      candles.map((c) => ({
        time: (c.ts / 1000) as Time,
        value: c.volume,
        color: c.close >= c.open ? "#22c55e40" : "#ef444440",
      }))
    );

    // 信号标注（买卖点标记）
    if (trades && trades.length > 0) {
      const markers = trades.flatMap((t) => {
        const result = [];
        // 入场标记
        result.push({
          time: (t.entry_ts / 1000) as Time,
          position: t.direction === "long" ? ("belowBar" as const) : ("aboveBar" as const),
          color: t.direction === "long" ? "#22c55e" : "#ef4444",
          shape: t.direction === "long" ? ("arrowUp" as const) : ("arrowDown" as const),
          text: `${t.direction === "long" ? "L" : "S"}${t.strength}`,
        });
        // 出场标记
        if (t.exit_ts) {
          result.push({
            time: (t.exit_ts / 1000) as Time,
            position: t.direction === "long" ? ("aboveBar" as const) : ("belowBar" as const),
            color: t.pnl > 0 ? "#22c55e" : "#ef4444",
            shape: "circle" as const,
            text: `${t.pnl > 0 ? "+" : ""}${t.pnl_pct.toFixed(1)}%`,
          });
        }
        return result;
      });

      // 按时间排序
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      createSeriesMarkers(candleSeries, markers);
    }

    // 自适应宽度
    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, trades, signals, height]);

  return <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />;
}
