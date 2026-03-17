import { useState, useEffect } from 'react';
import { X, TrendingUp, TrendingDown, BarChart3 } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  CartesianGrid,
} from 'recharts';
import { api } from '../hooks/useApi';

function IndicatorSection({ title, items }) {
  return (
    <div className="space-y-1">
      <h4
        className="text-[10px] uppercase font-semibold tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        {title}
      </h4>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {items.map(
          ({ label, value, color }) =>
            value != null && (
              <div key={label} className="flex justify-between text-xs py-0.5">
                <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                <span className="font-mono" style={{ color: color || 'var(--text-primary)' }}>
                  {typeof value === 'number' ? value.toFixed(5) : value}
                </span>
              </div>
            )
        )}
      </div>
    </div>
  );
}

export default function MarketDetail({ epic, market, onClose }) {
  const [priceData, setPriceData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [resolution, setResolution] = useState('HOUR');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getMarketPrices(epic, resolution, 50)
      .then((data) => {
        if (cancelled) return;
        const rows = (data.prices || [])
          .map((p) => {
            const close = p.closePrice?.bid;
            if (close == null) return null;
            return {
              time: p.snapshotTime,
              close,
              high: p.highPrice?.bid,
              low: p.lowPrice?.bid,
              open: p.openPrice?.bid,
            };
          })
          .filter(Boolean);
        setPriceData(rows);
      })
      .catch(console.error)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [epic, resolution]);

  const signal = market?.signal;
  const indicators = signal?.indicators || {};

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal header */}
        <div
          className="flex items-center justify-between p-4 border-b sticky top-0 z-10"
          style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
        >
          <div>
            <h2 className="text-lg font-bold">{market?.instrumentName || epic}</h2>
            <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
              {epic}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:opacity-80"
            style={{ background: 'var(--bg-secondary)' }}
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-6">
          {/* Price Chart */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <BarChart3 size={16} style={{ color: 'var(--accent-blue)' }} />
                Price Chart
              </h3>
              <div className="flex gap-1">
                {['MINUTE_5', 'MINUTE_15', 'HOUR', 'HOUR_4', 'DAY'].map((r) => (
                  <button
                    key={r}
                    onClick={() => setResolution(r)}
                    className="px-2.5 py-1 rounded text-xs font-medium transition"
                    style={{
                      background:
                        resolution === r ? 'var(--accent-blue)' : 'var(--bg-secondary)',
                      color: resolution === r ? '#fff' : 'var(--text-secondary)',
                    }}
                  >
                    {r.replace('MINUTE_', '').replace('HOUR_', '').replace('HOUR', '1H').replace('DAY', '1D')}
                    {r.includes('MINUTE') && 'm'}
                    {r === 'HOUR_4' && 'H'}
                  </button>
                ))}
              </div>
            </div>
            <div className="rounded-xl p-3" style={{ background: 'var(--bg-secondary)' }}>
              {loading ? (
                <div className="h-64 flex items-center justify-center" style={{ color: 'var(--text-secondary)' }}>
                  Loading chart...
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={priceData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis
                      dataKey="time"
                      tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
                      tickFormatter={(v) => {
                        const d = new Date(v);
                        return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
                      }}
                    />
                    <YAxis
                      domain={['auto', 'auto']}
                      tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
                      tickFormatter={(v) => v.toFixed(4)}
                      width={70}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border)',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      labelFormatter={(v) => new Date(v).toLocaleString()}
                    />
                    {indicators.volatility?.bb_upper && (
                      <ReferenceLine
                        y={indicators.volatility.bb_upper}
                        stroke="var(--accent-red)"
                        strokeDasharray="5 5"
                        strokeOpacity={0.5}
                      />
                    )}
                    {indicators.volatility?.bb_lower && (
                      <ReferenceLine
                        y={indicators.volatility.bb_lower}
                        stroke="var(--accent-green)"
                        strokeDasharray="5 5"
                        strokeOpacity={0.5}
                      />
                    )}
                    <Line
                      type="monotone"
                      dataKey="close"
                      stroke="var(--accent-blue)"
                      dot={false}
                      strokeWidth={2}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Signal Info */}
          {signal && (
            <div
              className="rounded-xl p-4"
              style={{ background: 'var(--bg-secondary)' }}
            >
              <div className="flex items-center gap-3 mb-3">
                <span
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold"
                  style={{
                    background:
                      signal.direction === 'BUY'
                        ? 'rgba(0,230,118,0.2)'
                        : signal.direction === 'SELL'
                        ? 'rgba(255,82,82,0.2)'
                        : 'rgba(139,143,163,0.2)',
                    color:
                      signal.direction === 'BUY'
                        ? 'var(--accent-green)'
                        : signal.direction === 'SELL'
                        ? 'var(--accent-red)'
                        : 'var(--text-secondary)',
                  }}
                >
                  {signal.direction === 'BUY' ? (
                    <TrendingUp size={16} />
                  ) : signal.direction === 'SELL' ? (
                    <TrendingDown size={16} />
                  ) : null}
                  {signal.direction}
                </span>
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  Confidence: <strong style={{ color: 'var(--accent-yellow)' }}>{(signal.confidence * 100).toFixed(0)}%</strong>
                </span>
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  SL: <strong style={{ color: 'var(--accent-red)' }}>{signal.stop_distance}</strong>
                </span>
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  TP: <strong style={{ color: 'var(--accent-green)' }}>{signal.limit_distance}</strong>
                </span>
              </div>

              {signal.reasons?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {signal.reasons.map((r, i) => (
                    <span
                      key={i}
                      className="text-[11px] px-2 py-1 rounded-md"
                      style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)' }}
                    >
                      {r}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Indicator Details */}
          {indicators && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <IndicatorSection
                title="Trend"
                items={[
                  { label: 'EMA 9', value: indicators.trend?.ema_9 },
                  { label: 'EMA 21', value: indicators.trend?.ema_21 },
                  { label: 'EMA 50', value: indicators.trend?.ema_50 },
                  { label: 'MACD', value: indicators.trend?.macd },
                  { label: 'MACD Signal', value: indicators.trend?.macd_signal },
                  { label: 'MACD Hist', value: indicators.trend?.macd_histogram },
                  { label: 'ADX', value: indicators.trend?.adx },
                  { label: 'DI+', value: indicators.trend?.adx_pos },
                  { label: 'DI-', value: indicators.trend?.adx_neg },
                ]}
              />
              <IndicatorSection
                title="Momentum"
                items={[
                  {
                    label: 'RSI(14)',
                    value: indicators.momentum?.rsi,
                    color:
                      indicators.momentum?.rsi > 70
                        ? 'var(--accent-red)'
                        : indicators.momentum?.rsi < 30
                        ? 'var(--accent-green)'
                        : undefined,
                  },
                  { label: 'Stoch %K', value: indicators.momentum?.stoch_k },
                  { label: 'Stoch %D', value: indicators.momentum?.stoch_d },
                  {
                    label: 'ROC Fast(9)',
                    value: indicators.momentum?.roc_fast != null
                      ? `${indicators.momentum.roc_fast > 0 ? '+' : ''}${indicators.momentum.roc_fast.toFixed(3)}%`
                      : null,
                    color: indicators.momentum?.roc_fast > 0
                      ? 'var(--accent-green)'
                      : indicators.momentum?.roc_fast < 0
                      ? 'var(--accent-red)'
                      : undefined,
                    rawValue: indicators.momentum?.roc_fast,
                  },
                  {
                    label: 'ROC Med(14)',
                    value: indicators.momentum?.roc_medium != null
                      ? `${indicators.momentum.roc_medium > 0 ? '+' : ''}${indicators.momentum.roc_medium.toFixed(3)}%`
                      : null,
                    color: indicators.momentum?.roc_medium > 0
                      ? 'var(--accent-green)'
                      : indicators.momentum?.roc_medium < 0
                      ? 'var(--accent-red)'
                      : undefined,
                    rawValue: indicators.momentum?.roc_medium,
                  },
                  {
                    label: 'ROC Slow(30)',
                    value: indicators.momentum?.roc_slow != null
                      ? `${indicators.momentum.roc_slow > 0 ? '+' : ''}${indicators.momentum.roc_slow.toFixed(3)}%`
                      : null,
                    color: indicators.momentum?.roc_slow > 0
                      ? 'var(--accent-green)'
                      : indicators.momentum?.roc_slow < 0
                      ? 'var(--accent-red)'
                      : undefined,
                    rawValue: indicators.momentum?.roc_slow,
                  },
                  {
                    label: 'ROC Composite',
                    value: indicators.momentum?.roc_composite != null
                      ? `${indicators.momentum.roc_composite > 0 ? '+' : ''}${indicators.momentum.roc_composite.toFixed(3)}%`
                      : null,
                    color: indicators.momentum?.roc_composite > 0
                      ? 'var(--accent-green)'
                      : indicators.momentum?.roc_composite < 0
                      ? 'var(--accent-red)'
                      : undefined,
                    rawValue: indicators.momentum?.roc_composite,
                  },
                ]}
              />
              <IndicatorSection
                title="Volatility"
                items={[
                  { label: 'BB Upper', value: indicators.volatility?.bb_upper },
                  { label: 'BB Middle', value: indicators.volatility?.bb_middle },
                  { label: 'BB Lower', value: indicators.volatility?.bb_lower },
                  { label: 'BB Width', value: indicators.volatility?.bb_width },
                  { label: 'ATR(14)', value: indicators.volatility?.atr },
                ]}
              />
              <IndicatorSection
                title="Price"
                items={[
                  { label: 'Open', value: indicators.price?.open },
                  { label: 'High', value: indicators.price?.high },
                  { label: 'Low', value: indicators.price?.low },
                  { label: 'Close', value: indicators.price?.close },
                  { label: 'Spread', value: indicators.price?.spread },
                ]}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
