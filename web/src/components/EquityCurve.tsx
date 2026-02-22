"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  ColorType,
  type Time,
  AreaSeries,
} from "lightweight-charts";
import type { EquityPoint } from "@/lib/types";

interface Props {
  data: EquityPoint[];
  initialCapital: number;
  height?: number;
}

export default function EquityCurve({ data, initialCapital, height = 250 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

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
      timeScale: {
        borderColor: "#374151",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "#374151",
      },
    });

    chartRef.current = chart;

    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: "#3b82f6",
      topColor: "#3b82f620",
      bottomColor: "#3b82f605",
      lineWidth: 2,
    });

    areaSeries.setData(
      data.map((p) => ({
        time: (p.ts / 1000) as Time,
        value: p.equity,
      }))
    );

    // 基准线（初始资金）
    areaSeries.createPriceLine({
      price: initialCapital,
      color: "#6b7280",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "初始资金",
    });

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
  }, [data, initialCapital, height]);

  return <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />;
}
