import pandas as pd
import numpy as np
import ta


def compute_indicators(prices_data: dict) -> pd.DataFrame:
    """
    Compute technical indicators from IG price data.
    Returns a DataFrame with OHLC + all indicator columns.
    """
    prices = prices_data.get("prices", [])
    if not prices:
        return pd.DataFrame()

    rows = []
    for p in prices:
        try:
            close_price = p.get("closePrice")
            high_price = p.get("highPrice")
            low_price = p.get("lowPrice")
            open_price = p.get("openPrice")

            # Skip candles where any OHLC object is missing entirely
            if not all([close_price, high_price, low_price, open_price]):
                continue

            close_bid = close_price.get("bid")
            close_ask = close_price.get("ask")
            high_bid = high_price.get("bid")
            low_bid = low_price.get("bid")
            open_bid = open_price.get("bid")

            if any(v is None for v in [close_bid, close_ask, high_bid, low_bid, open_bid]):
                continue
        except (AttributeError, TypeError, KeyError):
            continue

        mid_close = (close_bid + close_ask) / 2
        rows.append(
            {
                "timestamp": p["snapshotTime"],
                "open": open_bid,
                "high": high_bid,
                "low": low_bid,
                "close": close_bid,
                "mid_close": mid_close,
                "spread": close_ask - close_bid,
                "volume": p.get("lastTradedVolume", 0) or 0,
            }
        )

    if len(rows) < 20:
        return pd.DataFrame(rows)

    df = pd.DataFrame(rows)

    # --- Trend Indicators ---
    # EMA 9, 21, 50
    df["ema_9"] = ta.trend.ema_indicator(df["close"], window=9)
    df["ema_21"] = ta.trend.ema_indicator(df["close"], window=21)
    df["ema_50"] = ta.trend.ema_indicator(df["close"], window=min(50, len(df) - 1))

    # MACD
    macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()

    # ADX
    if len(df) >= 14:
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
        df["adx"] = adx.adx()
        df["adx_pos"] = adx.adx_pos()
        df["adx_neg"] = adx.adx_neg()

    # --- Momentum Indicators ---
    # RSI
    df["rsi"] = ta.momentum.rsi(df["close"], window=14)

    # Stochastic Oscillator
    if len(df) >= 14:
        stoch = ta.momentum.StochasticOscillator(
            df["high"], df["low"], df["close"], window=14, smooth_window=3
        )
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()

    # --- Volatility Indicators ---
    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()

    # ATR (Average True Range) - used for stop loss calculation
    if len(df) >= 14:
        atr = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], window=14
        )
        df["atr"] = atr.average_true_range()

    # --- Rate of Change (ROC) — Multi-timeframe momentum ---
    # Fast ROC (9): short-term momentum / entry signal
    df["roc_fast"] = ta.momentum.roc(df["close"], window=9)
    # Medium ROC (14): standard momentum confirmation
    df["roc_medium"] = ta.momentum.roc(df["close"], window=min(14, len(df) - 1))
    # Slow ROC (30): trend-level momentum filter
    if len(df) >= 31:
        df["roc_slow"] = ta.momentum.roc(df["close"], window=30)
    # Composite ROC score: weighted blend → 50% fast + 30% medium + 20% slow
    if "roc_slow" in df.columns:
        df["roc_composite"] = (
            0.50 * df["roc_fast"].fillna(0)
            + 0.30 * df["roc_medium"].fillna(0)
            + 0.20 * df["roc_slow"].fillna(0)
        )
    elif "roc_medium" in df.columns:
        df["roc_composite"] = (
            0.60 * df["roc_fast"].fillna(0)
            + 0.40 * df["roc_medium"].fillna(0)
        )
    else:
        df["roc_composite"] = df["roc_fast"]

    # --- Volume Indicators ---
    if df["volume"].sum() > 0:
        df["obv"] = ta.volume.on_balance_volume(df["close"], df["volume"])

    return df


def get_indicator_summary(df: pd.DataFrame) -> dict:
    """Extract the latest indicator values as a summary dict."""
    if df.empty:
        return {}

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    summary = {
        "price": {
            "open": _safe(latest.get("open")),
            "high": _safe(latest.get("high")),
            "low": _safe(latest.get("low")),
            "close": _safe(latest.get("close")),
            "spread": _safe(latest.get("spread")),
        },
        "trend": {
            "ema_9": _safe(latest.get("ema_9")),
            "ema_21": _safe(latest.get("ema_21")),
            "ema_50": _safe(latest.get("ema_50")),
            "macd": _safe(latest.get("macd")),
            "macd_signal": _safe(latest.get("macd_signal")),
            "macd_histogram": _safe(latest.get("macd_histogram")),
            "adx": _safe(latest.get("adx")),
            "adx_pos": _safe(latest.get("adx_pos")),
            "adx_neg": _safe(latest.get("adx_neg")),
        },
        "momentum": {
            "rsi": _safe(latest.get("rsi")),
            "stoch_k": _safe(latest.get("stoch_k")),
            "stoch_d": _safe(latest.get("stoch_d")),
            "roc_fast": _safe(latest.get("roc_fast")),
            "roc_medium": _safe(latest.get("roc_medium")),
            "roc_slow": _safe(latest.get("roc_slow")),
            "roc_composite": _safe(latest.get("roc_composite")),
        },
        "volatility": {
            "bb_upper": _safe(latest.get("bb_upper")),
            "bb_middle": _safe(latest.get("bb_middle")),
            "bb_lower": _safe(latest.get("bb_lower")),
            "bb_width": _safe(latest.get("bb_width")),
            "atr": _safe(latest.get("atr")),
        },
    }

    return summary


def _safe(val) -> float | None:
    """Convert to float, handling NaN/None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else round(f, 6)
    except (ValueError, TypeError):
        return None
