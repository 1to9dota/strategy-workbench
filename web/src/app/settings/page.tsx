"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSettings, getStrategies, updateSettings, updateStrategy, isLoggedIn } from "@/lib/api";
import type { Strategy, Settings } from "@/lib/types";

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  // 临时编辑状态
  const [pairsInput, setPairsInput] = useState("");

  useEffect(() => {
    if (!isLoggedIn()) { router.push("/login"); return; }
    (async () => {
      try {
        const [s, strats] = await Promise.all([
          getSettings(),
          getStrategies(),
        ]);
        setSettings(s);
        setStrategies(strats);
        setPairsInput(s.monitored_pairs.join(", "));
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, [router]);

  const save = async (key: string, value: unknown) => {
    setSaving(true);
    try {
      await updateSettings(key, value);
      setMsg("已保存");
      setTimeout(() => setMsg(""), 2000);
    } catch (e) {
      setMsg("保存失败: " + (e as Error).message);
    } finally { setSaving(false); }
  };

  const toggleStrategy = async (id: string, currentEnabled: number) => {
    const newEnabled = currentEnabled ? 0 : 1;
    await updateStrategy(id, { enabled: newEnabled });
    setStrategies((prev) => prev.map((s) => s.id === id ? { ...s, enabled: newEnabled } : s));
  };

  const saveStrategyParams = async (id: string, params: Record<string, number>) => {
    setSaving(true);
    try {
      await updateStrategy(id, { params });
      setMsg("策略参数已保存");
      setTimeout(() => setMsg(""), 2000);
    } catch (e) {
      setMsg("保存失败");
    } finally { setSaving(false); }
  };

  if (loading || !settings) {
    return <div className="min-h-screen bg-[#0a0b0f] flex items-center justify-center text-gray-500">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-[#0a0b0f] p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">参数配置</h1>
        <div className="flex items-center gap-3">
          {msg && <span className="text-sm text-green-400">{msg}</span>}
          <a href="/" className="text-sm text-gray-400 hover:text-white">Dashboard</a>
        </div>
      </div>

      {/* 合约参数 */}
      <Section title="合约参数">
        <Row label="杠杆倍数">
          <select value={settings.leverage}
            onChange={(e) => { const v = Number(e.target.value); setSettings({ ...settings, leverage: v }); save("leverage", v); }}
            className="bg-gray-800 text-white px-3 py-1.5 rounded border border-gray-700">
            {[1, 2, 3, 5, 10, 20].map((v) => <option key={v} value={v}>{v}x</option>)}
          </select>
        </Row>
        <Row label="保证金模式">
          <select value={settings.margin_mode}
            onChange={(e) => { setSettings({ ...settings, margin_mode: e.target.value }); save("margin_mode", e.target.value); }}
            className="bg-gray-800 text-white px-3 py-1.5 rounded border border-gray-700">
            <option value="isolated">逐仓 (isolated)</option>
            <option value="cross">全仓 (cross)</option>
          </select>
        </Row>
      </Section>

      {/* 监控配置 */}
      <Section title="监控配置">
        <Row label="监控币种">
          <div className="flex gap-2 items-center">
            <input value={pairsInput} onChange={(e) => setPairsInput(e.target.value)}
              className="bg-gray-800 text-white px-3 py-1.5 rounded border border-gray-700 flex-1 text-sm"
              placeholder="BTC-USDT-SWAP, ETH-USDT-SWAP" />
            <button onClick={() => {
              const pairs = pairsInput.split(",").map((s) => s.trim()).filter(Boolean);
              setSettings({ ...settings, monitored_pairs: pairs });
              save("monitored_pairs", pairs);
            }} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded cursor-pointer">
              保存
            </button>
          </div>
        </Row>
        <Row label="监控周期">
          <div className="flex gap-2 flex-wrap">
            {["1H", "2H", "4H", "6H", "12H", "1D"].map((b) => {
              const active = settings.monitored_bars.includes(b);
              return (
                <button key={b} onClick={() => {
                  const bars = active ? settings.monitored_bars.filter((x) => x !== b) : [...settings.monitored_bars, b];
                  setSettings({ ...settings, monitored_bars: bars });
                  save("monitored_bars", bars);
                }} className={`px-3 py-1 text-sm rounded cursor-pointer ${
                  active ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                }`}>{b}</button>
              );
            })}
          </div>
        </Row>
        <Row label="最低信号强度">
          <div className="flex gap-2">
            {[1, 2, 3].map((v) => (
              <button key={v} onClick={() => { setSettings({ ...settings, min_signal_strength: v }); save("min_signal_strength", v); }}
                className={`px-3 py-1 text-sm rounded cursor-pointer ${
                  settings.min_signal_strength === v ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400"
                }`}>
                {"★".repeat(v)} ({v})
              </button>
            ))}
          </div>
        </Row>
      </Section>

      {/* 仓位规则 */}
      <Section title="仓位规则">
        {[
          { key: "strength_1_pct", label: "单策略信号 (★)" },
          { key: "strength_2_pct", label: "双策略共振 (★★)" },
          { key: "strength_3_pct", label: "三策略共振 (★★★)" },
          { key: "max_total_pct", label: "总仓位上限" },
        ].map(({ key, label }) => (
          <Row key={key} label={label}>
            <div className="flex items-center gap-2">
              <input type="number"
                value={settings.position_rules[key as keyof typeof settings.position_rules]}
                onChange={(e) => {
                  const rules = { ...settings.position_rules, [key]: Number(e.target.value) };
                  setSettings({ ...settings, position_rules: rules });
                }}
                className="bg-gray-800 text-white px-3 py-1.5 rounded border border-gray-700 w-20 text-sm" />
              <span className="text-gray-400 text-sm">%</span>
            </div>
          </Row>
        ))}
        <div className="flex justify-end mt-2">
          <button onClick={() => save("position_rules", settings.position_rules)}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded cursor-pointer">
            保存仓位规则
          </button>
        </div>
      </Section>

      {/* 策略管理 */}
      <Section title="策略管理">
        {strategies.map((s) => (
          <div key={s.id} className="border border-gray-800 rounded-lg p-4 mb-3">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-white font-semibold">{s.name}</span>
                <span className="text-xs text-gray-500">{s.id}</span>
              </div>
              <button onClick={() => toggleStrategy(s.id, s.enabled)}
                className={`px-3 py-1 text-sm rounded cursor-pointer ${
                  s.enabled ? "bg-green-600/30 text-green-400" : "bg-gray-700 text-gray-400"
                }`}>
                {s.enabled ? "已启用" : "已禁用"}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(s.params).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2 text-sm">
                  <span className="text-gray-400 min-w-[100px]">{k}</span>
                  <input type="number" step="any" defaultValue={v}
                    onBlur={(e) => {
                      const newParams = { ...s.params, [k]: Number(e.target.value) };
                      setStrategies((prev) => prev.map((st) => st.id === s.id ? { ...st, params: newParams } : st));
                    }}
                    className="bg-gray-800 text-white px-2 py-1 rounded border border-gray-700 w-24 text-sm" />
                </div>
              ))}
            </div>
            <div className="flex justify-end mt-2">
              <button onClick={() => saveStrategyParams(s.id, s.params)}
                className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer">
                保存参数
              </button>
            </div>
          </div>
        ))}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold text-white mb-4 border-b border-gray-800 pb-2">{title}</h2>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-gray-300 text-sm">{label}</span>
      {children}
    </div>
  );
}
