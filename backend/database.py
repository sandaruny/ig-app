import sqlite3
import json
import logging
import os
from base64 import b64encode, b64decode

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ig_trader.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                username TEXT NOT NULL,
                password_b64 TEXT NOT NULL,
                api_key TEXT NOT NULL,
                api_url TEXT NOT NULL DEFAULT 'https://demo-api.ig.com/gateway/deal',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                epic TEXT NOT NULL UNIQUE,
                display_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sort_order INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS bot_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                trade_size REAL DEFAULT 1.0,
                max_positions INTEGER DEFAULT 10,
                analysis_interval INTEGER DEFAULT 300,
                min_confidence REAL DEFAULT 0.55,
                use_min_trade_size INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS epic_config (
                epic TEXT PRIMARY KEY,
                roc_period INTEGER DEFAULT 20,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id TEXT UNIQUE NOT NULL,
                epic TEXT NOT NULL,
                direction TEXT NOT NULL,
                size REAL NOT NULL,
                open_level REAL,
                stop_distance REAL,
                limit_distance REAL,
                stop_level REAL,
                limit_level REAL,
                currency TEXT DEFAULT 'USD',
                confidence REAL DEFAULT 0,
                signal_direction TEXT,
                signal_reasons TEXT,
                indicators TEXT,
                market_snapshot TEXT,
                status TEXT DEFAULT 'OPEN',
                pnl REAL,
                close_level REAL,
                opened_at TEXT,
                closed_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        # Migrations — add columns that may not exist in older DBs
        _migrate_add_column(conn, "bot_config", "min_confidence", "REAL DEFAULT 0.55")
        _migrate_add_column(conn, "bot_config", "use_min_trade_size", "INTEGER DEFAULT 0")

        logger.info("Database initialized at %s", DB_PATH)
    finally:
        conn.close()


def _migrate_add_column(conn: sqlite3.Connection, table: str, column: str, col_type: str):
    """Safely add a column if it doesn't already exist."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()
        logger.info("Migrated: added column %s.%s", table, column)
    except sqlite3.OperationalError:
        pass  # Column already exists


# ── Credentials ─────────────────────────────────────────────────


def save_credentials(username: str, password: str, api_key: str, api_url: str):
    """Save login credentials (password is base64 encoded, not plaintext)."""
    conn = _get_conn()
    try:
        pw_encoded = b64encode(password.encode("utf-8")).decode("utf-8")
        conn.execute(
            """INSERT INTO credentials (id, username, password_b64, api_key, api_url, updated_at)
               VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET
                   username = excluded.username,
                   password_b64 = excluded.password_b64,
                   api_key = excluded.api_key,
                   api_url = excluded.api_url,
                   updated_at = CURRENT_TIMESTAMP
            """,
            (username, pw_encoded, api_key, api_url),
        )
        conn.commit()
        logger.info("Credentials saved for user: %s", username)
    finally:
        conn.close()


def load_credentials() -> dict | None:
    """Load saved credentials. Returns dict with username, password, api_key, api_url or None."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM credentials WHERE id = 1").fetchone()
        if not row:
            return None
        return {
            "username": row["username"],
            "password": b64decode(row["password_b64"].encode("utf-8")).decode("utf-8"),
            "api_key": row["api_key"],
            "api_url": row["api_url"],
        }
    finally:
        conn.close()


def clear_credentials():
    """Remove saved credentials."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM credentials WHERE id = 1")
        conn.commit()
        logger.info("Credentials cleared")
    finally:
        conn.close()


# ── Watchlist ───────────────────────────────────────────────────


def save_watchlist(pairs: list[str]):
    """Replace the entire watchlist with a new list of epics."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM watchlist")
        for i, epic in enumerate(pairs):
            conn.execute(
                "INSERT OR IGNORE INTO watchlist (epic, sort_order) VALUES (?, ?)",
                (epic, i),
            )
        conn.commit()
        logger.info("Watchlist saved: %d pairs", len(pairs))
    finally:
        conn.close()


def load_watchlist() -> list[str]:
    """Load the watchlist from the database, ordered by sort_order."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT epic FROM watchlist ORDER BY sort_order ASC"
        ).fetchall()
        return [r["epic"] for r in rows]
    finally:
        conn.close()


def add_watchlist_pair(epic: str):
    """Add a single epic to the watchlist."""
    conn = _get_conn()
    try:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM watchlist"
        ).fetchone()["next_order"]
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (epic, sort_order) VALUES (?, ?)",
            (epic, max_order),
        )
        conn.commit()
    finally:
        conn.close()


def remove_watchlist_pair(epic: str):
    """Remove a single epic from the watchlist."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM watchlist WHERE epic = ?", (epic,))
        conn.commit()
    finally:
        conn.close()


# ── Bot Config ──────────────────────────────────────────────────


def save_bot_config(trade_size: float, max_positions: int, analysis_interval: int,
                    min_confidence: float = 0.55, use_min_trade_size: bool = False):
    """Save bot configuration."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO bot_config (id, trade_size, max_positions, analysis_interval,
                                       min_confidence, use_min_trade_size, updated_at)
               VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET
                   trade_size = excluded.trade_size,
                   max_positions = excluded.max_positions,
                   analysis_interval = excluded.analysis_interval,
                   min_confidence = excluded.min_confidence,
                   use_min_trade_size = excluded.use_min_trade_size,
                   updated_at = CURRENT_TIMESTAMP
            """,
            (trade_size, max_positions, analysis_interval, min_confidence,
             1 if use_min_trade_size else 0),
        )
        conn.commit()
    finally:
        conn.close()


def load_bot_config() -> dict | None:
    """Load saved bot configuration."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM bot_config WHERE id = 1").fetchone()
        if not row:
            return None
        result = {
            "trade_size": row["trade_size"],
            "max_positions": row["max_positions"],
            "analysis_interval": row["analysis_interval"],
        }
        # Columns that may not exist in older DBs
        try:
            result["min_confidence"] = row["min_confidence"]
        except (IndexError, KeyError):
            result["min_confidence"] = 0.55
        try:
            result["use_min_trade_size"] = bool(row["use_min_trade_size"])
        except (IndexError, KeyError):
            result["use_min_trade_size"] = False
        return result
    finally:
        conn.close()


# ── Trades ─────────────────────────────────────────────────────


def save_trade(trade_data: dict):
    """Insert or update a trade record."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO trades (
                deal_id, epic, direction, size, open_level,
                stop_distance, limit_distance, stop_level, limit_level,
                currency, confidence, signal_direction, signal_reasons,
                indicators, market_snapshot, status, pnl, close_level,
                opened_at, closed_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, CURRENT_TIMESTAMP
            )
            ON CONFLICT(deal_id) DO UPDATE SET
                status = excluded.status,
                pnl = excluded.pnl,
                close_level = excluded.close_level,
                closed_at = excluded.closed_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                trade_data.get("deal_id"),
                trade_data.get("epic"),
                trade_data.get("direction"),
                trade_data.get("size"),
                trade_data.get("open_level"),
                trade_data.get("stop_distance"),
                trade_data.get("limit_distance"),
                trade_data.get("stop_level"),
                trade_data.get("limit_level"),
                trade_data.get("currency", "USD"),
                trade_data.get("confidence", 0),
                trade_data.get("signal_direction"),
                json.dumps(trade_data.get("signal_reasons", [])),
                json.dumps(trade_data.get("indicators", {})),
                json.dumps(trade_data.get("market_snapshot", {})),
                trade_data.get("status", "OPEN"),
                trade_data.get("pnl"),
                trade_data.get("close_level"),
                trade_data.get("opened_at"),
                trade_data.get("closed_at"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_trade_status(deal_id: str, status: str, pnl: float = None,
                        close_level: float = None, closed_at: str = None):
    """Update the status and P&L of an existing trade."""
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE trades
               SET status = ?, pnl = ?, close_level = ?, closed_at = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE deal_id = ?""",
            (status, pnl, close_level, closed_at, deal_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_trade_pnl(deal_id: str, pnl: float):
    """Update just the P&L of an open trade."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE trades SET pnl = ?, updated_at = CURRENT_TIMESTAMP WHERE deal_id = ?",
            (pnl, deal_id),
        )
        conn.commit()
    finally:
        conn.close()


def load_trades(status: str = None) -> list[dict]:
    """Load trades from DB. Optionally filter by status ('OPEN' or 'CLOSED')."""
    conn = _get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            result.append({
                "deal_id": r["deal_id"],
                "epic": r["epic"],
                "direction": r["direction"],
                "size": r["size"],
                "open_level": r["open_level"],
                "stop_distance": r["stop_distance"],
                "limit_distance": r["limit_distance"],
                "stop_level": r["stop_level"],
                "limit_level": r["limit_level"],
                "currency": r["currency"],
                "confidence": r["confidence"],
                "signal_direction": r["signal_direction"],
                "signal_reasons": json.loads(r["signal_reasons"]) if r["signal_reasons"] else [],
                "indicators": json.loads(r["indicators"]) if r["indicators"] else {},
                "market_snapshot": json.loads(r["market_snapshot"]) if r["market_snapshot"] else {},
                "status": r["status"],
                "pnl": r["pnl"],
                "close_level": r["close_level"],
                "opened_at": r["opened_at"],
                "closed_at": r["closed_at"],
            })
        return result
    finally:
        conn.close()


def get_trade_by_deal_id(deal_id: str) -> dict | None:
    """Get a single trade by deal ID."""
    conn = _get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM trades WHERE deal_id = ?", (deal_id,)
        ).fetchone()
        if not r:
            return None
        return {
            "deal_id": r["deal_id"],
            "epic": r["epic"],
            "direction": r["direction"],
            "size": r["size"],
            "open_level": r["open_level"],
            "stop_distance": r["stop_distance"],
            "limit_distance": r["limit_distance"],
            "stop_level": r["stop_level"],
            "limit_level": r["limit_level"],
            "currency": r["currency"],
            "confidence": r["confidence"],
            "signal_direction": r["signal_direction"],
            "signal_reasons": json.loads(r["signal_reasons"]) if r["signal_reasons"] else [],
            "indicators": json.loads(r["indicators"]) if r["indicators"] else {},
            "market_snapshot": json.loads(r["market_snapshot"]) if r["market_snapshot"] else {},
            "status": r["status"],
            "pnl": r["pnl"],
            "close_level": r["close_level"],
            "opened_at": r["opened_at"],
            "closed_at": r["closed_at"],
        }
    finally:
        conn.close()


# ── Epic Config (per-epic indicator settings) ─────────────────


def save_epic_config(epic: str, roc_period: int):
    """Save per-epic indicator configuration."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO epic_config (epic, roc_period, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(epic) DO UPDATE SET
                   roc_period = excluded.roc_period,
                   updated_at = CURRENT_TIMESTAMP
            """,
            (epic, roc_period),
        )
        conn.commit()
    finally:
        conn.close()


def load_epic_configs() -> dict[str, dict]:
    """Load all per-epic configs. Returns {epic: {"roc_period": int}}."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT epic, roc_period FROM epic_config").fetchall()
        return {r["epic"]: {"roc_period": r["roc_period"]} for r in rows}
    finally:
        conn.close()


def get_epic_roc_period(epic: str, default: int = 20) -> int:
    """Get the ROC period for a specific epic, or the default."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT roc_period FROM epic_config WHERE epic = ?", (epic,)
        ).fetchone()
        return row["roc_period"] if row else default
    finally:
        conn.close()


# ── Auto-initialize on import ──────────────────────────────────
# Ensures tables exist before any endpoint can be called
init_db()
