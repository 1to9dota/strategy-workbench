"use client";

import type { Signal } from "@/lib/types";

interface Props {
  signal: Signal;
  onConfirm: (id: number) => void;
  onSkip: (id: number) => void;
}

export default function SignalCard({ signal, onConfirm, onSkip }: Props) {
  const isLong = signal.direction === "long";
  const strategies = (() => {
    try {
      return JSON.parse(signal.strategies);
    } catch {
      return [];
    }
  })();
  const strengthStars = Array(signal.strength).fill(null);

  // 止损距离百分比
  const slDistance = Math.abs(
    ((signal.stop_loss - signal.entry_price) / signal.entry_price) * 100
  ).toFixed(2);

  const isPending = signal.status === "pending";

  return (
    <div
      className={`border rounded-lg p-4 ${
        isLong
          ? "border-green-800 bg-green-950/30"
          : "border-red-800 bg-red-950/30"
      }`}
    >
      {/* 头部：币种 + 方向 + 强度 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className={`text-sm font-bold px-2 py-0.5 rounded ${
              isLong
                ? "bg-green-600/30 text-green-400"
                : "bg-red-600/30 text-red-400"
            }`}
          >
            {signal.direction.toUpperCase()}
          </span>
          <span className="font-semibold text-white">{signal.inst_id}</span>
          <span className="text-xs text-gray-400">{signal.bar}</span>
        </div>
        <div className="flex items-center gap-1">
          {strengthStars.map((_, i) => (
            <span key={i} className="text-yellow-400 text-sm">
              &#9733;
            </span>
          ))}
        </div>
      </div>

      {/* 价格信息 */}
      <div className="grid grid-cols-2 gap-2 mb-3 text-sm">
        <div>
          <span className="text-gray-400">入场价</span>
          <p className="text-white font-mono">{signal.entry_price.toFixed(2)}</p>
        </div>
        <div>
          <span className="text-gray-400">止损价</span>
          <p className="text-white font-mono">
            {signal.stop_loss.toFixed(2)}{" "}
            <span className="text-red-400 text-xs">(-{slDistance}%)</span>
          </p>
        </div>
      </div>

      {/* 策略标签 */}
      <div className="flex flex-wrap gap-1 mb-3">
        {strategies.map((s: string) => (
          <span
            key={s}
            className="text-xs bg-gray-700/50 text-gray-300 px-2 py-0.5 rounded"
          >
            {s}
          </span>
        ))}
        {signal.enter_tag && (
          <span className="text-xs bg-blue-800/30 text-blue-300 px-2 py-0.5 rounded">
            {signal.enter_tag}
          </span>
        )}
      </div>

      {/* 状态 + 操作按钮 */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">
          {new Date(signal.created_at).toLocaleString("zh-CN")}
        </span>
        {isPending ? (
          <div className="flex gap-2">
            <button
              onClick={() => onConfirm(signal.id)}
              className="px-3 py-1 text-sm bg-green-600 hover:bg-green-500 text-white rounded cursor-pointer"
            >
              确认下单
            </button>
            <button
              onClick={() => onSkip(signal.id)}
              className="px-3 py-1 text-sm bg-gray-600 hover:bg-gray-500 text-white rounded cursor-pointer"
            >
              跳过
            </button>
          </div>
        ) : (
          <span
            className={`text-xs px-2 py-0.5 rounded ${
              signal.status === "confirmed"
                ? "bg-green-800/30 text-green-400"
                : signal.status === "skipped"
                  ? "bg-gray-700/30 text-gray-400"
                  : "bg-yellow-800/30 text-yellow-400"
            }`}
          >
            {signal.status === "confirmed"
              ? "已确认"
              : signal.status === "skipped"
                ? "已跳过"
                : signal.status}
          </span>
        )}
      </div>
    </div>
  );
}
