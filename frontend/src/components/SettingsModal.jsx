import { useState, useEffect } from 'react';
import { X, Save, ShieldCheck, Minimize2 } from 'lucide-react';
import { api } from '../hooks/useApi';

export default function SettingsModal({ onClose }) {
  const [config, setConfig] = useState({
    tradeSize: 1,
    maxPositions: 10,
    analysisInterval: 300,
    minConfidence: 0.55,
    useMinTradeSize: false,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getConfig().then(setConfig).catch(console.error);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateConfig({
        tradeSize: config.tradeSize,
        maxPositions: config.maxPositions,
        analysisInterval: config.analysisInterval,
        minConfidence: config.minConfidence,
        useMinTradeSize: config.useMinTradeSize,
      });
      onClose();
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const confidencePct = Math.round((config.minConfidence || 0.55) * 100);
  const confColor =
    confidencePct >= 75
      ? 'var(--accent-green)'
      : confidencePct >= 55
      ? 'var(--accent-yellow)'
      : 'var(--accent-red)';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl max-h-[90vh] overflow-y-auto"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between p-4 border-b sticky top-0 z-10"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
        >
          <h2 className="text-lg font-bold">Bot Settings</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:opacity-80" style={{ background: 'var(--bg-secondary)' }}>
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Min Confidence — featured prominently */}
          <div
            className="rounded-xl p-4"
            style={{ background: 'var(--bg-secondary)', border: `1px solid ${confColor}33` }}
          >
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck size={18} style={{ color: confColor }} />
              <label className="text-sm font-semibold">
                Minimum Confidence to Trade
              </label>
            </div>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min="10"
                max="100"
                step="5"
                value={confidencePct}
                onChange={(e) =>
                  setConfig({ ...config, minConfidence: parseInt(e.target.value) / 100 })
                }
                className="flex-1 h-2 rounded-full appearance-none cursor-pointer"
                style={{
                  background: `linear-gradient(to right, ${confColor} 0%, ${confColor} ${confidencePct}%, var(--bg-card) ${confidencePct}%, var(--bg-card) 100%)`,
                  accentColor: confColor,
                }}
              />
              <span
                className="text-2xl font-bold font-mono tabular-nums"
                style={{ color: confColor, minWidth: 56, textAlign: 'right' }}
              >
                {confidencePct}%
              </span>
            </div>
            <p className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
              Only open positions when indicator score exceeds this threshold.
              Higher = fewer but stronger trades.
            </p>
            <div className="flex justify-between text-xs mt-2 font-mono" style={{ color: 'var(--text-secondary)' }}>
              <span>10% Aggressive</span>
              <span>55% Default</span>
              <span>100% Ultra-safe</span>
            </div>
          </div>

          {/* Use Minimum Trade Size toggle */}
          <div
            className="rounded-xl p-4"
            style={{
              background: 'var(--bg-secondary)',
              border: `1px solid ${config.useMinTradeSize ? 'var(--accent-green)' : 'var(--border)'}`,
            }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Minimize2 size={18} style={{ color: config.useMinTradeSize ? 'var(--accent-green)' : 'var(--text-secondary)' }} />
                <div>
                  <label className="text-sm font-semibold block">
                    Use Minimum Trade Size
                  </label>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                    Trade with the lowest allowed size per pair from IG
                  </p>
                </div>
              </div>
              <button
                onClick={() => setConfig({ ...config, useMinTradeSize: !config.useMinTradeSize })}
                className="relative w-12 h-6 rounded-full transition-colors duration-200 flex-shrink-0"
                style={{
                  background: config.useMinTradeSize ? 'var(--accent-green)' : 'var(--bg-card)',
                  border: `1px solid ${config.useMinTradeSize ? 'var(--accent-green)' : 'var(--border)'}`,
                }}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-4.5 h-4.5 rounded-full transition-transform duration-200"
                  style={{
                    width: 18,
                    height: 18,
                    background: config.useMinTradeSize ? '#fff' : 'var(--text-secondary)',
                    transform: config.useMinTradeSize ? 'translateX(24px)' : 'translateX(0)',
                  }}
                />
              </button>
            </div>
            {config.useMinTradeSize && (
              <div
                className="mt-3 text-xs px-3 py-2 rounded-lg"
                style={{ background: 'var(--bg-card)', color: 'var(--accent-green)' }}
              >
                Enabled — each trade will use IG's minimum deal size for that market
                (overrides Trade Size below). Ideal for testing with minimal risk.
              </div>
            )}
          </div>

          <div style={{ opacity: config.useMinTradeSize ? 0.4 : 1, pointerEvents: config.useMinTradeSize ? 'none' : 'auto' }}>
            <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
              Trade Size (lots)
            </label>
            <input
              type="number"
              step="0.1"
              min="0.1"
              value={config.tradeSize}
              onChange={(e) => setConfig({ ...config, tradeSize: parseFloat(e.target.value) })}
              className="w-full px-4 py-2.5 rounded-lg text-white outline-none"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
            />
            {config.useMinTradeSize && (
              <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                Disabled — minimum trade size toggle is active
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
              Max Open Positions
            </label>
            <input
              type="number"
              min="1"
              max="50"
              value={config.maxPositions}
              onChange={(e) => setConfig({ ...config, maxPositions: parseInt(e.target.value) })}
              className="w-full px-4 py-2.5 rounded-lg text-white outline-none"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
              Analysis Interval (seconds)
            </label>
            <input
              type="number"
              min="60"
              step="60"
              value={config.analysisInterval}
              onChange={(e) => setConfig({ ...config, analysisInterval: parseInt(e.target.value) })}
              className="w-full px-4 py-2.5 rounded-lg text-white outline-none"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
            />
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              How often the bot analyses markets (min: 60s)
            </p>
          </div>

          {config.currencyPairs && (
            <div>
              <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                Currency Pairs Monitored
              </label>
              <div className="flex flex-wrap gap-1.5">
                {config.currencyPairs.map((pair) => (
                  <span
                    key={pair}
                    className="text-xs px-2 py-1 rounded-md font-mono"
                    style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
                  >
                    {pair}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t sticky bottom-0" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            style={{ background: 'var(--accent-blue)' }}
          >
            <Save size={16} />
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
