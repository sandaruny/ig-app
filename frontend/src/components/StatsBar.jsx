import { TrendingUp, TrendingDown, BarChart3, DollarSign } from 'lucide-react';

export default function StatsBar({ trades, markets }) {
  const openTrades = trades.filter((t) => t.status === 'OPEN');
  const closedTrades = trades.filter((t) => t.status === 'CLOSED');
  const totalPnl = openTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
  const activeMarkets = Object.keys(markets).length;

  const buySignals = Object.values(markets).filter(
    (m) => m.signal?.direction === 'BUY'
  ).length;
  const sellSignals = Object.values(markets).filter(
    (m) => m.signal?.direction === 'SELL'
  ).length;

  const stats = [
    {
      label: 'Open Trades',
      value: openTrades.length,
      icon: BarChart3,
      color: 'var(--accent-blue)',
    },
    {
      label: 'Unrealised P&L',
      value: totalPnl >= 0 ? `+${totalPnl.toFixed(2)}` : totalPnl.toFixed(2),
      icon: DollarSign,
      color: totalPnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
    },
    {
      label: 'Buy Signals',
      value: buySignals,
      icon: TrendingUp,
      color: 'var(--accent-green)',
    },
    {
      label: 'Sell Signals',
      value: sellSignals,
      icon: TrendingDown,
      color: 'var(--accent-red)',
    },
    {
      label: 'Markets Tracked',
      value: activeMarkets,
      icon: BarChart3,
      color: 'var(--accent-yellow)',
    },
    {
      label: 'Closed Trades',
      value: closedTrades.length,
      icon: BarChart3,
      color: 'var(--text-secondary)',
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 p-4">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="rounded-xl p-4"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <stat.icon size={16} style={{ color: stat.color }} />
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              {stat.label}
            </span>
          </div>
          <div className="text-xl font-bold" style={{ color: stat.color }}>
            {stat.value}
          </div>
        </div>
      ))}
    </div>
  );
}
