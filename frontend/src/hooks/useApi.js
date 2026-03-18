const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.message || 'Request failed');
  }
  return res.json();
}

export const api = {
  login: (username, password, apiKey, isDemo) =>
    request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, apiKey, isDemo }),
    }),
  authStatus: () => request('/auth/status'),
  logout: () => request('/auth/logout', { method: 'POST' }),
  startTrader: () => request('/trader/start', { method: 'POST' }),
  stopTrader: () => request('/trader/stop', { method: 'POST' }),
  getState: () => request('/trader/state'),
  triggerAnalysis: () => request('/trader/analyse', { method: 'POST' }),
  getPositions: () => request('/positions'),
  getMarket: (epic) => request(`/markets/${epic}`),
  getMarketPrices: (epic, resolution = 'HOUR', points = 50) =>
    request(`/markets/${epic}/prices?resolution=${resolution}&points=${points}`),
  getAccounts: () => request('/accounts'),
  getHistory: () => request('/history'),
  getTradeHistory: () => request('/trades/history'),
  getAllTrades: () => request('/trades/all'),
  getTradeDetail: (dealId) => request(`/trades/${dealId}`),
  getConfig: () => request('/config'),
  updateConfig: (config) =>
    request('/config', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  searchMarkets: (query) => request(`/search?q=${encodeURIComponent(query)}`),
  getWatchlist: () => request('/watchlist'),
  addToWatchlist: (epic) =>
    request('/watchlist/add', {
      method: 'POST',
      body: JSON.stringify({ epic }),
    }),
  removeFromWatchlist: (epic) =>
    request('/watchlist/remove', {
      method: 'POST',
      body: JSON.stringify({ epic }),
    }),
  reorderWatchlist: (pairs) =>
    request('/watchlist/reorder', {
      method: 'POST',
      body: JSON.stringify({ pairs }),
    }),
  getSyncStatus: () => request('/sync/status'),
  retryDeadLetters: () => request('/sync/retry-dead', { method: 'POST' }),
  getEpicConfig: (epic) => request(`/epic-config/${encodeURIComponent(epic)}`),
  updateEpicConfig: (epic, config) =>
    request(`/epic-config/${encodeURIComponent(epic)}`, {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  getAllEpicConfigs: () => request('/epic-config'),
};
