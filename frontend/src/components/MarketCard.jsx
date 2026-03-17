import { TrendingUp, TrendingDown, Minus, ChevronRight, Trash2 } from 'lucide-react';
import { api } from '../hooks/useApi';

function SignalBadge({ signal }) {
  if (!signal) return null;
  const dir = signal.direction;
  const conf = signal.confidence;

  const styles = {
    BUY: { bg: 'rgba(0,230,118,0.15)', color: 'var(--accent-green)', icon: TrendingUp },
    SELL: { bg: 'rgba(255,82,82,0.15)', color: 'var(--accent-red)', icon: TrendingDown },
    HOLD: { bg: 'rgba(139,143,163,0.15)', color: 'var(--text-secondary)', icon: Minus },
  };

  const s = styles[dir] || styles.HOLD;
  const Icon = s.icon;

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold"
      style={{ background: s.bg, color: s.color }}
    >
      <Icon size={12} />
      {dir} {conf > 0 ? `${(conf * 100).toFixed(0)}%` : ''}
    </span>
  );
}

function IndicatorRow({ label, value, format }) {
  if (value === null || value === undefined) return null;
  const display = format ? format(value) : typeof value === 'number' ? value.toFixed(4) : value;

  return (
    <div className="flex justify-between text-xs py-0.5">
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span className="font-mono">{display}</span>
    </div>
  );
}

export default function MarketCard({ market, onSelect, onRemoved }) {
  const { instrumentName, epic, bid, offer, high, low, change, changePct, marketStatus, signal } =
    market;

  const isUp = change >= 0;
  const isForbidden = marketStatus === 'FORBIDDEN';
  const isExpired = marketStatus === 'SESSION_EXPIRED';
  const hasError = isForbidden || isExpired;

  const handleRemove = async (e) => {
    e.stopPropagation();
    try {
      await api.removeFromWatchlist(epic);
      if (onRemoved) onRemoved(epic);
    } catch (err) {
      console.error('Failed to remove from watchlist:', err);
    }
  };

  return (
    <div
      className="rounded-xl p-4 cursor-pointer transition-all hover:scale-[1.01]"
      style={{
        background: 'var(--bg-card)',
        border: `1px solid ${hasError ? 'rgba(255,82,82,0.3)' : 'var(--border)'}`,
        opacity: hasError ? 0.6 : 1,
      }}
      onClick={() => !hasError && onSelect(epic)}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-sm">{instrumentName || epic}</h3>
          <p className="text-xs font-mono mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            {epic}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SignalBadge signal={signal} />
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{
              background:
                marketStatus === 'TRADEABLE'
                  ? 'rgba(0,230,118,0.15)'
                  : 'rgba(255,82,82,0.15)',
              color:
                marketStatus === 'TRADEABLE'
                  ? 'var(--accent-green)'
                  : 'var(--accent-red)',
            }}
          >
            {marketStatus || 'N/A'}
          </span>
        </div>
      </div>

      {/* Error banner with remove button */}
      {hasError && (
        <div
          className="flex items-center justify-between gap-2 text-xs px-3 py-2 rounded-lg mb-3"
          style={{
            background: isExpired ? 'rgba(255,171,0,0.1)' : 'rgba(255,82,82,0.1)',
            color: isExpired ? 'var(--accent-yellow)' : 'var(--accent-red)',
          }}
        >
          <span>
            {market.error || (isExpired
              ? 'Session expired — please re-login'
              : 'No access — remove from watchlist')}
          </span>
          {isForbidden && (
            <button
              onClick={handleRemove}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs font-semibold shrink-0 transition-opacity hover:opacity-80"
              style={{ background: 'rgba(255,82,82,0.2)', color: 'var(--accent-red)' }}
            >
              <Trash2 size={12} />
              Remove
            </button>
          )}
        </div>
      )}

      {/* Price */}
      <div className="flex items-end gap-3 mb-3">
        <span className="text-2xl font-bold font-mono">
          {bid != null ? bid.toFixed(5) : '—'}
        </span>
        <span
          className="text-sm font-semibold flex items-center gap-0.5"
          style={{ color: isUp ? 'var(--accent-green)' : 'var(--accent-red)' }}
        >
          {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          {change != null ? `${isUp ? '+' : ''}${change}` : '—'}
          {changePct != null && (
            <span className="ml-1 text-xs">({changePct}%)</span>
          )}
        </span>
      </div>

      {/* Price Range */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div
          className="rounded-lg px-3 py-2"
          style={{ background: 'var(--bg-secondary)' }}
        >
          <div className="text-[10px] uppercase" style={{ color: 'var(--text-secondary)' }}>
            Bid
          </div>
          <div className="font-mono text-sm">{bid?.toFixed(5) ?? '—'}</div>
        </div>
        <div
          className="rounded-lg px-3 py-2"
          style={{ background: 'var(--bg-secondary)' }}
        >
          <div className="text-[10px] uppercase" style={{ color: 'var(--text-secondary)' }}>
            Offer
          </div>
          <div className="font-mono text-sm">{offer?.toFixed(5) ?? '—'}</div>
        </div>
      </div>

      {/* Key Indicators */}
      {signal?.indicators && (
        <div className="space-y-0.5">
          <IndicatorRow label="RSI(14)" value={signal.indicators.momentum?.rsi} format={(v) => v.toFixed(1)} />
          <IndicatorRow label="MACD" value={signal.indicators.trend?.macd} />
          <IndicatorRow label="EMA 9" value={signal.indicators.trend?.ema_9} />
          <IndicatorRow label="EMA 21" value={signal.indicators.trend?.ema_21} />
          <IndicatorRow label="BB Width" value={signal.indicators.volatility?.bb_width} />
          <IndicatorRow label="ATR(14)" value={signal.indicators.volatility?.atr} />
          <IndicatorRow label="ADX" value={signal.indicators.trend?.adx} format={(v) => v.toFixed(1)} />
        </div>
      )}

      {/* Signal Reasons */}
      {signal?.reasons?.length > 0 && (
        <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border)' }}>
          <div className="text-[10px] uppercase mb-1" style={{ color: 'var(--text-secondary)' }}>
            Signal Reasons
          </div>
          <div className="space-y-0.5">
            {signal.reasons.map((r, i) => (
              <div key={i} className="flex items-start gap-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <ChevronRight size={10} className="mt-0.5 shrink-0" />
                {r}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stop/Limit */}
      {signal && signal.direction !== 'HOLD' && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div
            className="rounded-lg px-3 py-2 text-center"
            style={{ background: 'rgba(255,82,82,0.1)' }}
          >
            <div className="text-[10px] uppercase" style={{ color: 'var(--accent-red)' }}>
              Stop Loss
            </div>
            <div className="font-mono text-sm" style={{ color: 'var(--accent-red)' }}>
              {signal.stop_distance}
            </div>
          </div>
          <div
            className="rounded-lg px-3 py-2 text-center"
            style={{ background: 'rgba(0,230,118,0.1)' }}
          >
            <div className="text-[10px] uppercase" style={{ color: 'var(--accent-green)' }}>
              Take Profit
            </div>
            <div className="font-mono text-sm" style={{ color: 'var(--accent-green)' }}>
              {signal.limit_distance}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
