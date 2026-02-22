// 后端数据类型定义

export interface Candle {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface BacktestRequest {
  inst_id: string;
  bar: string;
  start_date: string;
  end_date: string;
  strategies: string[];
  min_strength: number;
  initial_capital: number;
  name?: string;
}

export interface TagStats {
  count: number;
  wins: number;
  total_pnl: number;
}

export interface BacktestReport {
  initial_capital: number;
  final_capital: number;
  total_return_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  best_trade_pct: number;
  worst_trade_pct: number;
  buy_hold_return_pct: number;
  signals_count: number;
  tag_stats: Record<string, TagStats>;
}

export interface BacktestTrade {
  direction: "long" | "short";
  entry_price: number;
  entry_ts: number;
  exit_price: number;
  exit_ts: number;
  position_size: number;
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
  strategies: string[];
  enter_tag: string;
  strength: number;
  leverage: number;
}

export interface EquityPoint {
  ts: number;
  equity: number;
}

export interface BacktestSignal {
  direction: "long" | "short";
  strength: number;
  strategies: string[];
  entry_price: number;
  stop_loss: number;
  enter_tag: string;
  ts: number;
  price: number;
}

export interface BacktestResult {
  report: BacktestReport;
  trades: BacktestTrade[];
  equity_curve: EquityPoint[];
}

export interface BacktestHistory {
  id: number;
  name: string;
  inst_id: string;
  bar: string;
  start_date: string;
  end_date: string;
  strategies: string[];
  min_strength: number;
  result: BacktestReport;
  created_at: string;
}

export interface Strategy {
  id: string;
  name: string;
  enabled: number;
  params: Record<string, number>;
}

export interface Signal {
  id: number;
  inst_id: string;
  bar: string;
  direction: "long" | "short";
  strength: number;
  strategies: string;  // JSON string
  entry_price: number;
  stop_loss: number;
  enter_tag: string | null;
  status: "pending" | "confirmed" | "skipped" | "expired";
  created_at: string;
}

// OKX 持仓（来自 OKX API 原始字段）
export interface OKXPosition {
  instId: string;
  pos: string;
  posSide: string;
  avgPx: string;
  upl: string;
  uplRatio: string;
  lever: string;
  margin: string;
  mgnMode: string;
}

// 本地交易记录（来自数据库）
export interface TradeRecord {
  id: number;
  signal_id: number;
  inst_id: string;
  direction: "long" | "short";
  entry_price: number;
  exit_price: number | null;
  entry_time: string;
  exit_time: string | null;
  exit_reason: string | null;
  position_size: number;
  pnl: number | null;
  pnl_pct: number | null;
  leverage: number;
  margin_mode: string;
  created_at: string;
}

// 统计数据
export interface TradeStats {
  count: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  best: number;
  worst: number;
  profit_factor: number;
  period?: string;
}

// 系统配置
export interface Settings {
  leverage: number;
  margin_mode: string;
  monitored_pairs: string[];
  monitored_bars: string[];
  min_signal_strength: number;
  position_rules: {
    strength_1_pct: number;
    strength_2_pct: number;
    strength_3_pct: number;
    max_total_pct: number;
  };
  roi_table: Record<string, number>;
}
