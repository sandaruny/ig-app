import { useState, useEffect, useCallback } from 'react';
import './index.css';
import { api } from './hooks/useApi';
import { useWebSocket } from './hooks/useWebSocket';
import LoginPanel from './components/LoginPanel';
import Header from './components/Header';
import StatsBar from './components/StatsBar';
import MarketCard from './components/MarketCard';
import TradesTable from './components/TradesTable';
import MarketDetail from './components/MarketDetail';
import MarketSearch from './components/MarketSearch';
import SettingsModal from './components/SettingsModal';

function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [state, setState] = useState({ running: false, trades: [], markets: {} });
  const [selectedEpic, setSelectedEpic] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [activeTab, setActiveTab] = useState('markets');

  const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;
  const { data: wsData, connected } = useWebSocket(wsUrl);

  // Update state from WebSocket
  useEffect(() => {
    if (wsData) setState(wsData);
  }, [wsData]);

  // Check auth on mount, and if already authenticated fetch initial state (including open positions)
  useEffect(() => {
    api.authStatus().then((s) => {
      setAuthenticated(s.authenticated);
      if (s.authenticated) {
        api.getState().then(setState).catch(() => {});
      }
    }).catch(() => {});
  }, []);

  // Poll state when WS is disconnected
  useEffect(() => {
    if (connected || !authenticated) return;
    const interval = setInterval(() => {
      api.getState().then(setState).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [connected, authenticated]);

  const handleLogin = useCallback(async (username, password) => {
    await api.login(username, password);
    setAuthenticated(true);
    // Fetch initial state
    const s = await api.getState();
    setState(s);
  }, []);

  const handleStart = useCallback(async () => {
    await api.startTrader();
    setState((prev) => ({ ...prev, running: true }));
  }, []);

  const handleStop = useCallback(async () => {
    await api.stopTrader();
    setState((prev) => ({ ...prev, running: false }));
  }, []);

  const handleAnalyse = useCallback(async () => {
    setAnalysing(true);
    try {
      const s = await api.triggerAnalysis();
      setState(s);
    } catch (err) {
      console.error(err);
    } finally {
      setAnalysing(false);
    }
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await api.logout();
    } catch (err) {
      console.error(err);
    }
    setAuthenticated(false);
    setState({ running: false, trades: [], markets: {} });
  }, []);

  if (!authenticated) {
    return <LoginPanel onLogin={handleLogin} />;
  }

  const markets = Object.values(state.markets || {});
  const trades = state.trades || [];

  return (
    <div className="min-h-screen flex flex-col">
      <Header
        running={state.running}
        connected={connected}
        onStart={handleStart}
        onStop={handleStop}
        onAnalyse={handleAnalyse}
        onShowSettings={() => setShowSettings(true)}
        onLogout={handleLogout}
        analysing={analysing}
        syncRetry={state.syncRetry}
      />

      <StatsBar trades={trades} markets={state.markets || {}} />

      {/* Tab navigation */}
      <div className="px-4 flex gap-1" style={{ borderBottom: '1px solid var(--border)' }}>
        {[
          { id: 'markets', label: 'Markets', count: markets.length },
          { id: 'search', label: 'Search & Watchlist' },
          { id: 'trades', label: 'Trades', count: trades.length },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="px-4 py-3 text-sm font-medium transition-colors relative"
            style={{
              color:
                activeTab === tab.id
                  ? 'var(--accent-blue)'
                  : 'var(--text-secondary)',
            }}
          >
            {tab.label}
            {tab.count != null && (
              <span
                className="ml-1.5 text-xs px-1.5 py-0.5 rounded-full"
                style={{
                  background:
                    activeTab === tab.id
                      ? 'rgba(68,138,255,0.2)'
                      : 'var(--bg-card)',
                }}
              >
                {tab.count}
              </span>
            )}
            {activeTab === tab.id && (
              <span
                className="absolute bottom-0 left-0 right-0 h-0.5"
                style={{ background: 'var(--accent-blue)' }}
              />
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 p-4">
        {activeTab === 'markets' && (
          <>
            {markets.length === 0 ? (
              <div
                className="rounded-xl p-12 text-center"
                style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
              >
                <p className="text-lg mb-2">No market data yet</p>
                <p style={{ color: 'var(--text-secondary)' }}>
                  Click "Analyse" or start the bot to scan currency pairs.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {markets.map((m) => (
                  <MarketCard
                    key={m.epic}
                    market={m}
                    onSelect={setSelectedEpic}
                    onRemoved={(epic) => {
                      setState((prev) => {
                        const newMarkets = { ...prev.markets };
                        delete newMarkets[epic];
                        return { ...prev, markets: newMarkets };
                      });
                    }}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {activeTab === 'search' && <MarketSearch />}

        {activeTab === 'trades' && <TradesTable trades={trades} />}
      </div>

      {/* Modals */}
      {selectedEpic && (
        <MarketDetail
          epic={selectedEpic}
          market={state.markets?.[selectedEpic]}
          onClose={() => setSelectedEpic(null)}
        />
      )}

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}

export default App;
