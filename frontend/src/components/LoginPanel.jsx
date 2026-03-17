import { useState } from 'react';
import { LogIn, AlertCircle } from 'lucide-react';

export default function LoginPanel({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await onLogin(username, password);
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
            Connect to your IG demo account to start trading
          </p>
        </div>

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
              className="w-full px-4 py-3 rounded-lg text-white outline-none focus:ring-2"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                focusRingColor: 'var(--accent-blue)',
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
              className="w-full px-4 py-3 rounded-lg text-white outline-none focus:ring-2"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
              }}
              placeholder="IG password"
              required
            />
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
            style={{ background: 'var(--accent-blue)' }}
          >
            {loading ? 'Connecting...' : 'Connect to IG'}
          </button>
        </form>

        <p className="text-center mt-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
          Demo account &middot; API Key configured
        </p>
      </div>
    </div>
  );
}
