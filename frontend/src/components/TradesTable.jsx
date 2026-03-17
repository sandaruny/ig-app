import { useState, useEffect } from 'react';
import {
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Shield,
  Target,
  TrendingUp,
  History,
  Info,
  XCircle,
  Activity,
} from 'lucide-react';
import { api } from '../hooks/useApi';

// ── Confidence bar ──────────────────────────────────────────────
function ConfidenceBar({ confidence }) {
  const pct = Math.round((confidence || 0) * 100);
  const color =
    pct >= 75
      ? 'var(--accent-green)'
      : pct >= 55
      ? 'var(--accent-yellow)'
      : pct >= 1
      ? 'var(--accent-red)'
      : 'var(--text-secondary)';
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex-1 h-2 rounded-full overflow-hidden"
        style={{ background: 'var(--bg-secondary)', minWidth: 60 }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.max(pct, 2)}%`, background: color }}
        />
      </div>
      <span className="text-xs font-mono font-bold" style={{ color, minWidth: 32 }}>
        {pct > 0 ? `${pct}%` : '—'}
      </span>
    </div>
  );
}

// ── Stop / Limit visual ─────────────────────────────────────────
function StopLimitVisual({ trade }) {
  const { direction, openLevel, stopDistance, limitDistance, stopLevel, limitLevel, scalingFactor } = trade;
  const isBuy = direction === 'BUY';
  const pointSize = 1 / (scalingFactor || 10000);

  // Use absolute levels if available, otherwise compute from distance + scaling
  const sl = stopLevel != null
    ? stopLevel
    : openLevel != null
    ? (isBuy ? openLevel - stopDistance * pointSize : openLevel + stopDistance * pointSize)
    : null;

  const tp = limitLevel != null
    ? limitLevel
    : openLevel != null
    ? (isBuy ? openLevel + limitDistance * pointSize : openLevel - limitDistance * pointSize)
    : null;

  if (sl == null || tp == null || openLevel == null) {
    return (
      <div className="flex gap-4 text-xs font-mono">
        <span style={{ color: 'var(--accent-red)' }}>SL: {stopDistance ? `${stopDistance} pts` : '—'}</span>
        <span style={{ color: 'var(--accent-green)' }}>TP: {limitDistance ? `${limitDistance} pts` : '—'}</span>
      </div>
    );
  }

  // Visual range from SL to TP
  const totalRange = Math.abs(tp - sl) || 1;
  const openPct = Math.max(2, Math.min(98,
    (Math.abs(openLevel - Math.min(sl, tp)) / totalRange) * 100
  ));
  const riskReward = limitDistance && stopDistance ? (limitDistance / stopDistance).toFixed(1) : '—';

  // Determine price decimal places from scaling
  const decimals = scalingFactor >= 10000 ? 5 : scalingFactor >= 100 ? 3 : 2;

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs font-mono">
        <span style={{ color: 'var(--accent-red)' }}>
          SL: {stopDistance ? `${stopDistance} pts` : '—'}
        </span>
        <span style={{ color: 'var(--text-secondary)' }}>R:R {riskReward}</span>
        <span style={{ color: 'var(--accent-green)' }}>
          TP: {limitDistance ? `${limitDistance} pts` : '—'}
        </span>
      </div>
      <div className="relative h-3 rounded-full overflow-hidden" style={{ background: 'var(--bg-secondary)' }}>
        {/* Stop loss zone */}
        <div
          className="absolute top-0 bottom-0 left-0 rounded-l-full"
          style={{
            width: `${openPct}%`,
            background: 'linear-gradient(90deg, rgba(255,82,82,0.4), rgba(255,82,82,0.1))',
          }}
        />
        {/* Take profit zone */}
        <div
          className="absolute top-0 bottom-0 right-0 rounded-r-full"
          style={{
            width: `${100 - openPct}%`,
            background: 'linear-gradient(90deg, rgba(0,230,118,0.1), rgba(0,230,118,0.4))',
          }}
        />
        {/* Open level marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5"
          style={{
            left: `${openPct}%`,
            background: 'var(--accent-blue)',
            boxShadow: '0 0 4px var(--accent-blue)',
          }}
        />
      </div>
      <div className="flex justify-between text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
        <span style={{ color: 'var(--accent-red)' }}>{sl.toFixed(decimals)}</span>
        <span style={{ color: 'var(--accent-blue)' }}>{openLevel.toFixed(decimals)}</span>
        <span style={{ color: 'var(--accent-green)' }}>{tp.toFixed(decimals)}</span>
      </div>
    </div>
  );
}

// ── Indicator pills ─────────────────────────────────────────────
function IndicatorPills({ indicators }) {
  if (!indicators || Object.keys(indicators).length === 0) return null;

  const pills = [];
  if (indicators.rsi != null) {
    const rsi = indicators.rsi;
    const color = rsi < 30 ? 'var(--accent-green)' : rsi > 70 ? 'var(--accent-red)' : 'var(--text-secondary)';
    pills.push({ label: 'RSI', value: typeof rsi === 'number' ? rsi.toFixed(1) : rsi, color });
  }
  if (indicators.macd != null) {
    const macd = indicators.macd;
    const color = macd > 0 ? 'var(--accent-green)' : 'var(--accent-red)';
    pills.push({ label: 'MACD', value: typeof macd === 'number' ? macd.toFixed(5) : macd, color });
  }
  if (indicators.adx != null) {
    const adx = indicators.adx;
    const color = adx > 25 ? 'var(--accent-yellow)' : 'var(--text-secondary)';
    pills.push({ label: 'ADX', value: typeof adx === 'number' ? adx.toFixed(1) : adx, color });
  }
  if (indicators.stoch_k != null) {
    const k = indicators.stoch_k;
    const color = k < 20 ? 'var(--accent-green)' : k > 80 ? 'var(--accent-red)' : 'var(--text-secondary)';
    pills.push({ label: 'Stoch K', value: typeof k === 'number' ? k.toFixed(1) : k, color });
  }
  if (indicators.atr != null) {
    pills.push({ label: 'ATR', value: typeof indicators.atr === 'number' ? indicators.atr.toFixed(5) : indicators.atr, color: 'var(--accent-blue)' });
  }
  if (indicators.bb_position != null) {
    pills.push({ label: 'BB Pos', value: indicators.bb_position, color: 'var(--text-secondary)' });
  }
  if (indicators.ema_trend != null) {
    pills.push({ label: 'EMA', value: indicators.ema_trend, color: indicators.ema_trend === 'Bullish' ? 'var(--accent-green)' : 'var(--accent-red)' });
  }

  if (pills.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {pills.map((p) => (
        <span
          key={p.label}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono"
          style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            color: p.color,
          }}
        >
          <span style={{ color: 'var(--text-secondary)' }}>{p.label}</span>
          {p.value}
        </span>
      ))}
    </div>
  );
}

// ── Signal reasons list ─────────────────────────────────────────
function SignalReasons({ reasons }) {
  if (!reasons || reasons.length === 0) return null;
  return (
    <div className="space-y-0.5">
      {reasons.map((r, i) => (
        <div key={i} className="flex items-start gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--accent-blue)' }}>&#8226;</span>
          {r}
        </div>
      ))}
    </div>
  );
}

// ── Expandable trade row ────────────────────────────────────────
function TradeRow({ trade }) {
  const [expanded, setExpanded] = useState(false);
  const isBuy = trade.direction === 'BUY';
  const isOpen = trade.status === 'OPEN';
  const pnl = trade.pnl;
  const signal = trade.signal || {};
  // Use top-level confidence (populated by backend), fall back to signal.confidence
  const confidence = trade.confidence != null ? trade.confidence : (signal.confidence || 0);
  const decimals = (trade.scalingFactor || 10000) >= 10000 ? 5 : (trade.scalingFactor || 10000) >= 100 ? 3 : 2;

  return (
    <>
      <tr
        className="transition-colors cursor-pointer hover:brightness-110"
        style={{ borderBottom: expanded ? 'none' : '1px solid var(--border)' }}
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-4 py-3">
          <span
            className="inline-flex items-center gap-1 text-xs font-medium"
            style={{
              color: isOpen ? 'var(--accent-blue)' : pnl != null && pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
            }}
          >
            {isOpen ? <Clock size={12} /> : pnl != null && pnl >= 0 ? <CheckCircle size={12} /> : <XCircle size={12} />}
            {trade.status}
          </span>
        </td>
        <td className="px-4 py-3 font-mono text-xs">{trade.epic}</td>
        <td className="px-4 py-3">
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold"
            style={{
              background: isBuy ? 'rgba(0,230,118,0.15)' : 'rgba(255,82,82,0.15)',
              color: isBuy ? 'var(--accent-green)' : 'var(--accent-red)',
            }}
          >
            {isBuy ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {trade.direction}
          </span>
        </td>
        <td className="px-4 py-3 font-mono">{trade.size}</td>
        <td className="px-4 py-3 font-mono">{trade.openLevel != null ? trade.openLevel.toFixed(decimals) : '—'}</td>
        <td className="px-4 py-3" style={{ minWidth: 120 }}>
          <ConfidenceBar confidence={confidence} />
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-3 text-xs font-mono">
            <span style={{ color: 'var(--accent-red)' }}>
              <Shield size={10} className="inline mr-0.5" />
              {trade.stopDistance != null ? `${trade.stopDistance}` : '—'}
            </span>
            <span style={{ color: 'var(--accent-green)' }}>
              <Target size={10} className="inline mr-0.5" />
              {trade.limitDistance != null ? `${trade.limitDistance}` : '—'}
            </span>
          </div>
        </td>
        <td
          className="px-4 py-3 font-mono font-semibold"
          style={{
            color:
              pnl == null
                ? 'var(--text-secondary)'
                : pnl >= 0
                ? 'var(--accent-green)'
                : 'var(--accent-red)',
          }}
        >
          {pnl != null ? (pnl >= 0 ? `+${pnl.toFixed(2)}` : pnl.toFixed(2)) : '—'}
        </td>
        <td className="px-4 py-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
          {trade.openedAt ? new Date(trade.openedAt).toLocaleString() : '—'}
        </td>
        <td className="px-4 py-3">
          {expanded ? (
            <ChevronUp size={14} style={{ color: 'var(--text-secondary)' }} />
          ) : (
            <ChevronDown size={14} style={{ color: 'var(--text-secondary)' }} />
          )}
        </td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          <td colSpan={10} className="px-4 py-4" style={{ background: 'var(--bg-secondary)' }}>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Stop / Limit visualization */}
              <div
                className="rounded-lg p-3 space-y-2"
                style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-center gap-1.5 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  <Shield size={12} /> Stop / Take Profit
                </div>
                <StopLimitVisual trade={trade} />
              </div>

              {/* Indicators */}
              <div
                className="rounded-lg p-3 space-y-2"
                style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-center gap-1.5 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  <Activity size={12} /> Indicators at Entry
                </div>
                <IndicatorPills indicators={signal.indicators} />
                {(!signal.indicators || Object.keys(signal.indicators).length === 0) && (
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>No indicator data recorded</p>
                )}
              </div>

              {/* Signal reasons */}
              <div
                className="rounded-lg p-3 space-y-2"
                style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-center gap-1.5 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  <Info size={12} /> Decision Reasons
                </div>
                <SignalReasons reasons={signal.reasons} />
                {(!signal.reasons || signal.reasons.length === 0) && (
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>No reason data recorded</p>
                )}
              </div>
            </div>

            {/* Confidence detail */}
            <div
              className="mt-3 rounded-lg p-3"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Trade Confidence
                </span>
                <span className="text-sm font-bold font-mono" style={{
                  color: confidence >= 0.75 ? 'var(--accent-green)' : confidence >= 0.55 ? 'var(--accent-yellow)' : 'var(--accent-red)',
                }}>
                  {confidence > 0 ? `${Math.round(confidence * 100)}%` : 'N/A'}
                </span>
              </div>
              <ConfidenceBar confidence={confidence} />
            </div>

            {/* Extra details row */}
            <div className="mt-3 flex flex-wrap gap-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
              {trade.currency && <span>Currency: <strong>{trade.currency}</strong></span>}
              {trade.dealId && <span>Deal ID: <strong className="font-mono">{trade.dealId}</strong></span>}
              {trade.closedAt && <span>Closed: <strong>{new Date(trade.closedAt).toLocaleString()}</strong></span>}
              {trade.closeLevel != null && <span>Close Level: <strong className="font-mono">{trade.closeLevel.toFixed(decimals)}</strong></span>}
              {trade.stopLevel != null && <span>Stop Level: <strong className="font-mono">{trade.stopLevel.toFixed(decimals)}</strong></span>}
              {trade.limitLevel != null && <span>Limit Level: <strong className="font-mono">{trade.limitLevel.toFixed(decimals)}</strong></span>}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Summary stats for a trades section ──────────────────────────
function TradesSummary({ trades, label }) {
  if (!trades.length) return null;
  const totalPnl = trades.reduce((sum, t) => sum + (t.pnl || 0), 0);
  const wins = trades.filter((t) => t.pnl != null && t.pnl > 0).length;
  const losses = trades.filter((t) => t.pnl != null && t.pnl < 0).length;
  const confs = trades.map((t) => t.confidence || t.signal?.confidence || 0);
  const avgConf = confs.reduce((s, c) => s + c, 0) / trades.length;

  return (
    <div className="flex flex-wrap gap-3 mb-3">
      {[
        { label: `${label}`, value: trades.length, color: 'var(--accent-blue)' },
        {
          label: 'Total P&L',
          value: totalPnl >= 0 ? `+${totalPnl.toFixed(2)}` : totalPnl.toFixed(2),
          color: totalPnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
        },
        { label: 'Wins', value: wins, color: 'var(--accent-green)' },
        { label: 'Losses', value: losses, color: 'var(--accent-red)' },
        { label: 'Avg Confidence', value: avgConf > 0 ? `${Math.round(avgConf * 100)}%` : '—', color: 'var(--accent-yellow)' },
      ].map((s) => (
        <div
          key={s.label}
          className="rounded-lg px-3 py-2 text-center"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', minWidth: 80 }}
        >
          <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{s.label}</div>
          <div className="text-sm font-bold font-mono" style={{ color: s.color }}>{s.value}</div>
        </div>
      ))}
    </div>
  );
}

// ── Table component used for both sections ──────────────────────
function TradesTableSection({ trades, emptyMessage }) {
  if (!trades.length) {
    return (
      <div
        className="rounded-xl p-6 text-center"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
      >
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--bg-secondary)' }}>
              {['Status', 'Epic', 'Dir', 'Size', 'Open Level', 'Confidence', 'Stop / Limit', 'P&L', 'Opened', ''].map(
                (h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {trades.map((trade, i) => (
              <TradeRow key={trade.dealId || i} trade={trade} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────
export default function TradesTable({ trades }) {
  const [activeSection, setActiveSection] = useState('open');
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const openTrades = (trades || []).filter((t) => t.status === 'OPEN');
  const closedFromState = (trades || []).filter((t) => t.status === 'CLOSED');

  // Load history from DB
  useEffect(() => {
    if (activeSection === 'history') {
      setLoadingHistory(true);
      api.getTradeHistory()
        .then((res) => {
          // Merge with state closed trades, deduplicate by dealId
          const stateIds = new Set(closedFromState.map((t) => t.dealId));
          const dbOnly = (res.trades || [])
            .filter((t) => !stateIds.has(t.deal_id))
            .map(mapDbTrade);
          setHistory([...closedFromState, ...dbOnly]);
        })
        .catch(() => setHistory(closedFromState))
        .finally(() => setLoadingHistory(false));
    }
  }, [activeSection]);

  const sections = [
    { id: 'open', label: 'Active Trades', icon: TrendingUp, count: openTrades.length },
    { id: 'history', label: 'Trade History', icon: History, count: history.length || closedFromState.length },
  ];

  return (
    <div className="space-y-4">
      {/* Section tabs */}
      <div className="flex gap-2">
        {sections.map((sec) => (
          <button
            key={sec.id}
            onClick={() => setActiveSection(sec.id)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all"
            style={{
              background: activeSection === sec.id ? 'var(--accent-blue)' : 'var(--bg-card)',
              color: activeSection === sec.id ? '#fff' : 'var(--text-secondary)',
              border: `1px solid ${activeSection === sec.id ? 'var(--accent-blue)' : 'var(--border)'}`,
            }}
          >
            <sec.icon size={14} />
            {sec.label}
            <span
              className="text-xs px-1.5 py-0.5 rounded-full"
              style={{
                background: activeSection === sec.id ? 'rgba(255,255,255,0.2)' : 'var(--bg-secondary)',
              }}
            >
              {sec.count}
            </span>
          </button>
        ))}
      </div>

      {/* Active trades */}
      {activeSection === 'open' && (
        <>
          <TradesSummary trades={openTrades} label="Open Positions" />
          <TradesTableSection
            trades={openTrades}
            emptyMessage="No active trades. Start the bot or click Analyse to scan for opportunities."
          />
        </>
      )}

      {/* Trade history */}
      {activeSection === 'history' && (
        <>
          {loadingHistory ? (
            <div
              className="rounded-xl p-8 text-center"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
            >
              <div className="inline-block w-5 h-5 border-2 rounded-full animate-spin mb-2"
                style={{ borderColor: 'var(--border)', borderTopColor: 'var(--accent-blue)' }}
              />
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Loading trade history...</p>
            </div>
          ) : (
            <>
              <TradesSummary trades={history} label="Closed Trades" />
              <TradesTableSection
                trades={history}
                emptyMessage="No trade history yet. Completed trades will appear here with full indicator data."
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

/** Map DB snake_case trade record to camelCase for the UI components */
function mapDbTrade(t) {
  const snapshot = t.market_snapshot || {};
  return {
    dealId: t.deal_id,
    epic: t.epic,
    direction: t.direction,
    size: t.size,
    openLevel: t.open_level,
    stopDistance: t.stop_distance,
    limitDistance: t.limit_distance,
    stopLevel: t.stop_level,
    limitLevel: t.limit_level,
    currency: t.currency,
    status: t.status,
    pnl: t.pnl,
    closeLevel: t.close_level,
    openedAt: t.opened_at,
    closedAt: t.closed_at,
    confidence: t.confidence || 0,
    scalingFactor: snapshot.scalingFactor || 10000,
    signal: {
      direction: t.signal_direction,
      confidence: t.confidence || 0,
      reasons: t.signal_reasons || [],
      indicators: t.indicators || {},
    },
  };
}
