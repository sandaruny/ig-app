import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Search,
  Plus,
  X,
  Check,
  Loader2,
  Trash2,
  Star,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Globe,
  ShieldAlert,
} from 'lucide-react';
import { api } from '../hooks/useApi';

// ── Debounce hook ──────────────────────────────────────────────
function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

// ── Instrument type badge colours ──────────────────────────────
const TYPE_COLORS = {
  CURRENCIES: { bg: 'rgba(68,138,255,0.15)', color: 'var(--accent-blue)' },
  INDICES: { bg: 'rgba(0,230,118,0.15)', color: 'var(--accent-green)' },
  COMMODITIES: { bg: 'rgba(255,215,64,0.15)', color: 'var(--accent-yellow)' },
  SHARES: { bg: 'rgba(192,132,252,0.15)', color: '#c084fc' },
  RATES: { bg: 'rgba(255,82,82,0.15)', color: 'var(--accent-red)' },
};

// ── Contract type badge colours ────────────────────────────────
const CONTRACT_COLORS = {
  CFD: { bg: 'rgba(0,230,118,0.15)', color: 'var(--accent-green)', label: 'CFD' },
  MINI: { bg: 'rgba(255,171,0,0.15)', color: 'var(--accent-yellow)', label: 'MINI' },
  TODAY: { bg: 'rgba(68,138,255,0.15)', color: 'var(--accent-blue)', label: 'TODAY' },
  IFD: { bg: 'rgba(192,132,252,0.15)', color: '#c084fc', label: 'IFD' },
  DAILY: { bg: 'rgba(139,143,163,0.15)', color: 'var(--text-secondary)', label: 'DAILY' },
};

function getTypeStyle(type) {
  return TYPE_COLORS[type] || { bg: 'rgba(139,143,163,0.15)', color: 'var(--text-secondary)' };
}

function getContractStyle(ct) {
  return CONTRACT_COLORS[ct] || { bg: 'rgba(139,143,163,0.15)', color: 'var(--text-secondary)', label: ct || '?' };
}

// ── Search result row ──────────────────────────────────────────
function SearchResultRow({ market, onAdd, onRemove, adding, addError }) {
  const {
    epic,
    instrumentName,
    instrumentType,
    contractType,
    bid,
    offer,
    netChange,
    percentageChange,
    marketStatus,
    watched,
    demoRestricted,
    demoWarning,
  } = market;

  const isUp = (netChange ?? 0) >= 0;
  const typeStyle = getTypeStyle(instrumentType);
  const ctStyle = getContractStyle(contractType);
  const isRestricted = demoRestricted === true;
  const errorForThis = addError?.epic === epic ? addError.msg : null;

  return (
    <div
      className="px-4 py-3 transition-colors"
      style={{
        borderBottom: '1px solid var(--border)',
        opacity: isRestricted ? 0.5 : 1,
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-secondary)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <div className="flex items-center gap-3">
        {/* Type + contract badges */}
        <div className="flex flex-col gap-1 shrink-0">
          <span
            className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded text-center"
            style={{ background: typeStyle.bg, color: typeStyle.color }}
          >
            {instrumentType || 'N/A'}
          </span>
          <span
            className="text-[10px] font-bold uppercase px-2 py-0.5 rounded text-center"
            style={{ background: ctStyle.bg, color: ctStyle.color }}
          >
            {ctStyle.label}
          </span>
        </div>

        {/* Market info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">{instrumentName}</span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded shrink-0"
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
              {marketStatus || '—'}
            </span>
            {isRestricted && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded shrink-0 flex items-center gap-0.5"
                style={{ background: 'rgba(255,82,82,0.15)', color: 'var(--accent-red)' }}
              >
                <ShieldAlert size={10} /> Restricted
              </span>
            )}
          </div>
          <span
            className="text-xs font-mono block truncate"
            style={{ color: 'var(--text-secondary)' }}
          >
            {epic}
          </span>
          {demoWarning && !isRestricted && (
            <span className="text-[10px] block mt-0.5" style={{ color: 'var(--accent-yellow)' }}>
              {demoWarning}
            </span>
          )}
        </div>

        {/* Prices */}
        <div className="text-right shrink-0 mr-2">
          {bid != null ? (
            <>
              <div className="font-mono text-sm">
                <span style={{ color: 'var(--text-secondary)' }}>B</span>{' '}
                {bid}
                <span className="mx-1" style={{ color: 'var(--border)' }}>/</span>
                <span style={{ color: 'var(--text-secondary)' }}>A</span>{' '}
                {offer}
              </div>
              <div
                className="text-xs font-mono flex items-center justify-end gap-1"
                style={{ color: isUp ? 'var(--accent-green)' : 'var(--accent-red)' }}
              >
                {isUp ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                {netChange != null && (isUp ? '+' : '')}
                {netChange ?? '—'}
                {percentageChange != null && (
                  <span className="opacity-70">({percentageChange}%)</span>
                )}
              </div>
            </>
          ) : (
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              No price
            </span>
          )}
        </div>

        {/* Add/Remove button */}
        {watched ? (
          <button
            onClick={() => onRemove(epic)}
            disabled={adding === epic}
            className="shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity hover:opacity-80 disabled:opacity-50"
            style={{
              background: 'rgba(255,82,82,0.15)',
              color: 'var(--accent-red)',
              border: '1px solid rgba(255,82,82,0.3)',
            }}
            title="Remove from watchlist"
          >
            {adding === epic ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            Watching
          </button>
        ) : (
          <button
            onClick={() => onAdd(epic)}
            disabled={adding === epic || isRestricted}
            className="shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-opacity hover:opacity-80 disabled:opacity-50"
            style={{
              background: isRestricted ? 'rgba(139,143,163,0.1)' : 'rgba(0,230,118,0.15)',
              color: isRestricted ? 'var(--text-secondary)' : 'var(--accent-green)',
              border: `1px solid ${isRestricted ? 'var(--border)' : 'rgba(0,230,118,0.3)'}`,
            }}
            title={isRestricted ? 'Not available on demo account' : 'Add to watchlist'}
          >
            {adding === epic ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            {isRestricted ? 'N/A' : 'Add'}
          </button>
        )}
      </div>

      {/* Inline validation error */}
      {errorForThis && (
        <div
          className="flex items-center gap-1.5 mt-2 ml-14 text-xs px-3 py-1.5 rounded-lg"
          style={{ background: 'rgba(255,82,82,0.1)', color: 'var(--accent-red)' }}
        >
          <AlertCircle size={12} />
          {errorForThis}
        </div>
      )}
    </div>
  );
}

// ── Watchlist pair chip ────────────────────────────────────────
function WatchlistChip({ epic, onRemove, removing }) {
  const short = epicToShortName(epic);

  return (
    <div
      className="group flex items-center gap-1.5 pl-3 pr-1.5 py-1.5 rounded-lg text-sm transition-all"
      style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
      }}
    >
      <Star size={12} style={{ color: 'var(--accent-yellow)' }} />
      <span className="font-medium">{short}</span>
      <span
        className="text-[10px] font-mono hidden sm:inline"
        style={{ color: 'var(--text-secondary)' }}
      >
        {epic}
      </span>
      <button
        onClick={() => onRemove(epic)}
        disabled={removing === epic}
        className="ml-1 p-1 rounded-md opacity-50 hover:opacity-100 transition-opacity"
        style={{ color: 'var(--accent-red)' }}
        title="Remove"
      >
        {removing === epic ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <X size={12} />
        )}
      </button>
    </div>
  );
}

function epicToShortName(epic) {
  const parts = epic.split('.');
  for (const p of parts) {
    if (/^[A-Z]{6}$/.test(p)) {
      return p.slice(0, 3) + '/' + p.slice(3);
    }
    if (/^[A-Z]{3}[A-Z]{3}$/.test(p)) {
      return p.slice(0, 3) + '/' + p.slice(3);
    }
  }
  if (parts.length >= 3) return parts.slice(0, 3).join('.');
  return epic;
}

// ── Main MarketSearch Component ────────────────────────────────
export default function MarketSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [watchlist, setWatchlist] = useState([]);
  const [actionEpic, setActionEpic] = useState(null);
  const [addError, setAddError] = useState(null); // {epic, msg}
  const [hasSearched, setHasSearched] = useState(false);

  const debouncedQuery = useDebounce(query, 400);
  const inputRef = useRef(null);

  // Load watchlist on mount
  useEffect(() => {
    api.getWatchlist().then((data) => setWatchlist(data.pairs || [])).catch(console.error);
  }, []);

  // Auto-search when debounced query changes
  useEffect(() => {
    if (!debouncedQuery || debouncedQuery.length < 2) {
      if (!debouncedQuery) {
        setResults([]);
        setHasSearched(false);
      }
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    setAddError(null);
    api
      .searchMarkets(debouncedQuery)
      .then((data) => {
        if (cancelled) return;
        setResults(data.markets || []);
        setHasSearched(true);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message);
        setHasSearched(true);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery]);

  // Re-annotate results when watchlist changes
  useEffect(() => {
    const set = new Set(watchlist);
    setResults((prev) => prev.map((r) => ({ ...r, watched: set.has(r.epic) })));
  }, [watchlist]);

  const handleAdd = useCallback(async (epic) => {
    setActionEpic(epic);
    setAddError(null);
    try {
      const res = await api.addToWatchlist(epic);
      if (res.status === 'forbidden' || res.status === 'not_found') {
        // Validation failed — show error inline
        setAddError({ epic, msg: res.error || 'Cannot add this market' });
        // Mark it as restricted in results
        setResults((prev) =>
          prev.map((r) =>
            r.epic === epic ? { ...r, demoRestricted: true } : r
          )
        );
      } else {
        setWatchlist(res.pairs);
      }
    } catch (err) {
      console.error('Failed to add:', err);
      setAddError({ epic, msg: err.message || 'Failed to add market' });
    } finally {
      setActionEpic(null);
    }
  }, []);

  const handleRemove = useCallback(async (epic) => {
    setActionEpic(epic);
    setAddError(null);
    try {
      const res = await api.removeFromWatchlist(epic);
      setWatchlist(res.pairs);
    } catch (err) {
      console.error('Failed to remove:', err);
    } finally {
      setActionEpic(null);
    }
  }, []);

  const handleClear = useCallback(() => {
    setQuery('');
    setResults([]);
    setHasSearched(false);
    setAddError(null);
    inputRef.current?.focus();
  }, []);

  // Quick search suggestions
  const suggestions = [
    { label: 'Forex', query: 'forex' },
    { label: 'EUR', query: 'EUR' },
    { label: 'GBP', query: 'GBP' },
    { label: 'USD', query: 'USD' },
    { label: 'JPY', query: 'JPY' },
    { label: 'AUD', query: 'AUD' },
    { label: 'Gold', query: 'gold' },
    { label: 'Oil', query: 'oil' },
    { label: 'Bitcoin', query: 'bitcoin' },
    { label: 'S&P 500', query: 'S&P 500' },
  ];

  return (
    <div className="space-y-4">
      {/* ── Current Watchlist ── */}
      <div
        className="rounded-xl p-4"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Star size={16} style={{ color: 'var(--accent-yellow)' }} />
            Active Watchlist
            <span
              className="text-xs px-1.5 py-0.5 rounded-full"
              style={{ background: 'rgba(255,215,64,0.15)', color: 'var(--accent-yellow)' }}
            >
              {watchlist.length}
            </span>
          </h3>
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            The bot trades only these pairs
          </span>
        </div>
        {watchlist.length === 0 ? (
          <div
            className="rounded-lg p-6 text-center"
            style={{ background: 'var(--bg-secondary)' }}
          >
            <Globe size={24} className="mx-auto mb-2" style={{ color: 'var(--text-secondary)' }} />
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              No pairs in watchlist. Search and add markets below.
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {watchlist.map((epic) => (
              <WatchlistChip
                key={epic}
                epic={epic}
                onRemove={handleRemove}
                removing={actionEpic}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Search Box ── */}
      <div
        className="rounded-xl overflow-hidden"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
      >
        <div className="p-4">
          <div className="relative">
            <Search
              size={18}
              className="absolute left-3.5 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--text-secondary)' }}
            />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search markets... (e.g. EUR/USD, Gold, Bitcoin, S&P 500)"
              className="w-full pl-10 pr-10 py-3 rounded-lg text-white outline-none text-sm"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
              }}
              autoFocus
            />
            {query && (
              <button
                onClick={handleClear}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded hover:opacity-80"
                style={{ color: 'var(--text-secondary)' }}
              >
                <X size={16} />
              </button>
            )}
          </div>

          {/* Quick suggestions */}
          {!query && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              <span className="text-xs mr-1 self-center" style={{ color: 'var(--text-secondary)' }}>
                Quick:
              </span>
              {suggestions.map((s) => (
                <button
                  key={s.query}
                  onClick={() => setQuery(s.query)}
                  className="text-xs px-2.5 py-1 rounded-md font-medium transition-all hover:opacity-80"
                  style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}

          {/* Hint about contract types */}
          {!query && (
            <div className="mt-3 flex items-start gap-2 text-[11px] px-3 py-2 rounded-lg"
              style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
            >
              <AlertCircle size={14} className="shrink-0 mt-0.5" />
              <span>
                <strong>Tip:</strong> Look for <span style={{ color: 'var(--accent-green)' }}>CFD</span> contracts
                — they work best on demo accounts.
                <span style={{ color: 'var(--accent-yellow)' }}> MINI</span> contracts are often restricted.
              </span>
            </div>
          )}
        </div>

        {/* Loading indicator */}
        {loading && (
          <div
            className="flex items-center justify-center gap-2 py-6"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <Loader2 size={18} className="animate-spin" style={{ color: 'var(--accent-blue)' }} />
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              Searching IG markets...
            </span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div
            className="flex items-center gap-2 px-4 py-3 text-sm"
            style={{
              borderTop: '1px solid var(--border)',
              background: 'rgba(255,82,82,0.07)',
              color: 'var(--accent-red)',
            }}
          >
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {/* Results */}
        {!loading && hasSearched && results.length === 0 && !error && (
          <div
            className="text-center py-8"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <Search size={24} className="mx-auto mb-2" style={{ color: 'var(--text-secondary)' }} />
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              No markets found for "{debouncedQuery}"
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              Try a different keyword like "EUR", "forex", or "gold"
            </p>
          </div>
        )}

        {!loading && results.length > 0 && (
          <div style={{ borderTop: '1px solid var(--border)' }}>
            <div
              className="flex items-center justify-between px-4 py-2"
              style={{ background: 'var(--bg-secondary)' }}
            >
              <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                {results.length} result{results.length !== 1 ? 's' : ''} for "{debouncedQuery}"
                <span className="ml-2 opacity-60">
                  (sorted: <span style={{ color: 'var(--accent-green)' }}>CFD</span> first)
                </span>
              </span>
              <span className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                Click <Plus size={10} className="inline" /> to add to watchlist
              </span>
            </div>
            <div className="max-h-[420px] overflow-y-auto">
              {results.map((market) => (
                <SearchResultRow
                  key={market.epic}
                  market={market}
                  onAdd={handleAdd}
                  onRemove={handleRemove}
                  adding={actionEpic}
                  addError={addError}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
