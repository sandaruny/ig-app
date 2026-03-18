import { useState, useEffect } from 'react';
import { LogIn, AlertCircle, Shield, Zap, Key, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../hooks/useApi';

export default function LoginPanel({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [isDemo, setIsDemo] = useState(true);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);

  // Pre-fill API key if saved credentials exist
  useEffect(() => {
    api.authStatus().then((s) => {
      if (s.apiKey) setApiKey(s.apiKey);
      if (s.environment === 'live') setIsDemo(false);
    }).catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await onLogin(username, password, apiKey, isDemo);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div
        className="w-full max-w-md rounded-2xl p-8"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
      >
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
            style={{ background: 'var(--accent-blue)', opacity: 0.9 }}
          >
            <LogIn size={28} color="#fff" />
          </div>
          <h1 className="text-2xl font-bold mb-2">IG Trading Bot</h1>
          <p style={{ color: 'var(--text-secondary)' }}>
            Connect to your IG account to start trading
          </p>
        </div>

        {/* Demo / Live toggle */}
        <div
          className="flex rounded-xl mb-6 p-1"
          style={{ background: 'var(--bg-secondary)' }}
        >
          <button
            type="button"
            onClick={() => setIsDemo(true)}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all"
            style={{
              background: isDemo ? 'var(--bg-card)' : 'transparent',
              color: isDemo ? 'var(--accent-blue)' : 'var(--text-secondary)',
              boxShadow: isDemo ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
            }}
          >
            <Shield size={16} />
            Demo
          </button>
          <button
            type="button"
            onClick={() => setIsDemo(false)}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all"
            style={{
              background: !isDemo ? 'var(--bg-card)' : 'transparent',
              color: !isDemo ? 'var(--accent-red)' : 'var(--text-secondary)',
              boxShadow: !isDemo ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
            }}
          >
            <Zap size={16} />
            Live
          </button>
        </div>

        {/* Live account warning */}
        {!isDemo && (
          <div
            className="flex items-start gap-2 p-3 rounded-lg text-sm mb-4"
            style={{ background: 'rgba(255,82,82,0.1)', color: 'var(--accent-red)' }}
          >
            <AlertCircle size={16} className="shrink-0 mt-0.5" />
            <span>
              <strong>Live account</strong> — trades will use real money.
              Make sure you understand the risks.
            </span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              className="block text-sm font-medium mb-1.5"
              style={{ color: 'var(--text-secondary)' }}
            >
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-3 rounded-lg text-white outline-none"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
              }}
              placeholder="IG username"
              required
            />
          </div>
          <div>
            <label
              className="block text-sm font-medium mb-1.5"
              style={{ color: 'var(--text-secondary)' }}
            >
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 rounded-lg text-white outline-none"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
              }}
              placeholder="IG password"
              required
            />
          </div>

          {/* API Key — collapsible */}
          <div>
            <button
              type="button"
              onClick={() => setShowApiKey(!showApiKey)}
              className="flex items-center gap-1.5 text-sm font-medium mb-1.5"
              style={{ color: 'var(--text-secondary)' }}
            >
              <Key size={14} />
              API Key
              {apiKey && !showApiKey && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded ml-1"
                  style={{ background: 'rgba(0,230,118,0.15)', color: 'var(--accent-green)' }}
                >
                  configured
                </span>
              )}
              {showApiKey ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {showApiKey && (
              <input
                type="text"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full px-4 py-3 rounded-lg text-white outline-none font-mono text-xs"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                }}
                placeholder="Your IG API key (from labs.ig.com)"
              />
            )}
            {showApiKey && (
              <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                Get your API key from{' '}
                <a
                  href="https://labs.ig.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--accent-blue)' }}
                >
                  labs.ig.com
                </a>
                . {isDemo ? 'Use a demo API key for demo.' : 'Use a live API key for live.'}
              </p>
            )}
          </div>

          {error && (
            <div
              className="flex items-center gap-2 p-3 rounded-lg text-sm"
              style={{ background: 'rgba(255,82,82,0.1)', color: 'var(--accent-red)' }}
            >
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            style={{
              background: isDemo ? 'var(--accent-blue)' : 'var(--accent-red)',
            }}
          >
            {loading
              ? 'Connecting...'
              : `Connect to IG ${isDemo ? 'Demo' : 'Live'}`}
          </button>
        </form>

        <div className="flex items-center justify-center gap-2 mt-4">
          <span
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full"
            style={{
              background: isDemo
                ? 'rgba(68,138,255,0.15)'
                : 'rgba(255,82,82,0.15)',
              color: isDemo ? 'var(--accent-blue)' : 'var(--accent-red)',
            }}
          >
            {isDemo ? <Shield size={12} /> : <Zap size={12} />}
            {isDemo ? 'demo-api.ig.com' : 'api.ig.com'}
          </span>
        </div>
      </div>
    </div>
  );
}
