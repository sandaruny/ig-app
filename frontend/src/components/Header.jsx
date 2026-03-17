import { Activity, Power, Play, Square, RefreshCw, Settings, LogOut, AlertTriangle, RotateCcw } from 'lucide-react';

export default function Header({
  running,
  connected,
  onStart,
  onStop,
  onAnalyse,
  onShowSettings,
  onLogout,
  analysing,
  syncRetry,
}) {
  const pending = syncRetry?.pending || 0;
  const dead = syncRetry?.dead || 0;
  const hasSyncIssues = pending > 0 || dead > 0;

  return (
    <header
      className="flex items-center justify-between px-6 py-4 border-b"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center gap-3">
        <Activity size={24} style={{ color: 'var(--accent-blue)' }} />
        <h1 className="text-xl font-bold">IG Trading Bot</h1>
        <span
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
          style={{
            background: running
              ? 'rgba(0,230,118,0.15)'
              : 'rgba(255,82,82,0.15)',
            color: running ? 'var(--accent-green)' : 'var(--accent-red)',
          }}
        >
          <span
            className="w-2 h-2 rounded-full"
            style={{
              background: running ? 'var(--accent-green)' : 'var(--accent-red)',
            }}
          />
          {running ? 'Running' : 'Stopped'}
        </span>
        <span
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs"
          style={{
            background: connected ? 'rgba(68,138,255,0.15)' : 'rgba(139,143,163,0.15)',
            color: connected ? 'var(--accent-blue)' : 'var(--text-secondary)',
          }}
        >
          <span
            className="w-2 h-2 rounded-full"
            style={{
              background: connected ? 'var(--accent-blue)' : 'var(--text-secondary)',
            }}
          />
          WS {connected ? 'Live' : 'Off'}
        </span>

        {/* Sync retry indicator */}
        {hasSyncIssues && (
          <span
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
            style={{
              background: dead > 0 ? 'rgba(255,82,82,0.15)' : 'rgba(255,171,0,0.15)',
              color: dead > 0 ? 'var(--accent-red)' : 'var(--accent-yellow)',
            }}
            title={`${pending} pending retries, ${dead} failed permanently`}
          >
            {dead > 0 ? <AlertTriangle size={12} /> : <RotateCcw size={12} className="animate-spin" style={{ animationDuration: '3s' }} />}
            Sync: {pending > 0 ? `${pending} retrying` : ''}{pending > 0 && dead > 0 ? ', ' : ''}{dead > 0 ? `${dead} failed` : ''}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onAnalyse}
          disabled={analysing}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-50"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
          title="Run analysis now"
        >
          <RefreshCw size={14} className={analysing ? 'animate-spin' : ''} />
          Analyse
        </button>

        {!running ? (
          <button
            onClick={onStart}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90"
            style={{ background: 'var(--accent-green)' }}
          >
            <Play size={14} />
            Start Bot
          </button>
        ) : (
          <button
            onClick={onStop}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90"
            style={{ background: 'var(--accent-red)' }}
          >
            <Square size={14} />
            Stop Bot
          </button>
        )}

        <button
          onClick={onShowSettings}
          className="p-2 rounded-lg transition-opacity hover:opacity-80"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          title="Settings"
        >
          <Settings size={16} style={{ color: 'var(--text-secondary)' }} />
        </button>

        <button
          onClick={onLogout}
          className="p-2 rounded-lg transition-opacity hover:opacity-80"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          title="Logout & clear saved credentials"
        >
          <LogOut size={16} style={{ color: 'var(--accent-red)' }} />
        </button>
      </div>
    </header>
  );
}
