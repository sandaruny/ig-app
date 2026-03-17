import logging
import pandas as pd
from indicators import compute_indicators, get_indicator_summary
from config import settings

logger = logging.getLogger(__name__)


class Signal:
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeSignal:
    def __init__(
        self,
        direction: str,
        confidence: float,
        stop_distance: float,
        limit_distance: float,
        reasons: list[str],
        indicators: dict,
    ):
        self.direction = direction
        self.confidence = confidence
        self.stop_distance = stop_distance
        self.limit_distance = limit_distance
        self.reasons = reasons
        self.indicators = indicators

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "confidence": round(self.confidence, 2),
            "stop_distance": round(self.stop_distance, 2),
            "limit_distance": round(self.limit_distance, 2),
            "reasons": self.reasons,
            "indicators": self.indicators,
        }


class TradingStrategy:
    """
    Multi-indicator strategy combining:
    - EMA crossover (trend)
    - RSI (momentum/overbought/oversold)
    - MACD (trend confirmation)
    - Bollinger Bands (volatility/mean reversion)
    - ADX (trend strength)
    - Stochastic (overbought/oversold)
    - Rate of Change / ROC (multi-timeframe momentum + conviction multiplier)
    - ATR (stop loss/take profit sizing)
    """

    RISK_REWARD_RATIO = 2.0  # Target profit = 2x risk

    @property
    def confidence_threshold(self) -> float:
        """Minimum confidence to trigger a trade — read from live settings."""
        return settings.min_confidence

    def analyse(self, prices_data: dict) -> TradeSignal:
        """Analyse price data and return a trade signal."""
        df = compute_indicators(prices_data)

        if df.empty or len(df) < 30:
            return TradeSignal(
                direction=Signal.HOLD,
                confidence=0.0,
                stop_distance=0,
                limit_distance=0,
                reasons=["Insufficient data for analysis"],
                indicators={},
            )

        indicators = get_indicator_summary(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        buy_score = 0.0
        sell_score = 0.0
        reasons_buy = []
        reasons_sell = []

        # --- 1. EMA Crossover (weight: 0.2) ---
        ema_9 = latest.get("ema_9")
        ema_21 = latest.get("ema_21")
        ema_50 = latest.get("ema_50")
        prev_ema_9 = prev.get("ema_9")
        prev_ema_21 = prev.get("ema_21")

        if _valid(ema_9, ema_21, prev_ema_9, prev_ema_21):
            # Bullish crossover: EMA9 crosses above EMA21
            if prev_ema_9 <= prev_ema_21 and ema_9 > ema_21:
                buy_score += 0.2
                reasons_buy.append("EMA 9/21 bullish crossover")
            elif prev_ema_9 >= prev_ema_21 and ema_9 < ema_21:
                sell_score += 0.2
                reasons_sell.append("EMA 9/21 bearish crossover")
            elif ema_9 > ema_21:
                buy_score += 0.1
                reasons_buy.append("EMA 9 above EMA 21 (uptrend)")
            else:
                sell_score += 0.1
                reasons_sell.append("EMA 9 below EMA 21 (downtrend)")

        # Price relative to EMA 50
        if _valid(ema_50):
            close = latest["close"]
            if close > ema_50:
                buy_score += 0.05
                reasons_buy.append("Price above EMA 50")
            else:
                sell_score += 0.05
                reasons_sell.append("Price below EMA 50")

        # --- 2. RSI (weight: 0.2) ---
        rsi = latest.get("rsi")
        if _valid(rsi):
            if rsi < 30:
                buy_score += 0.2
                reasons_buy.append(f"RSI oversold ({rsi:.1f})")
            elif rsi < 40:
                buy_score += 0.1
                reasons_buy.append(f"RSI approaching oversold ({rsi:.1f})")
            elif rsi > 70:
                sell_score += 0.2
                reasons_sell.append(f"RSI overbought ({rsi:.1f})")
            elif rsi > 60:
                sell_score += 0.1
                reasons_sell.append(f"RSI approaching overbought ({rsi:.1f})")

        # --- 3. MACD (weight: 0.2) ---
        macd = latest.get("macd")
        macd_signal = latest.get("macd_signal")
        macd_hist = latest.get("macd_histogram")
        prev_macd = prev.get("macd")
        prev_macd_signal = prev.get("macd_signal")

        if _valid(macd, macd_signal, prev_macd, prev_macd_signal):
            # MACD crossover
            if prev_macd <= prev_macd_signal and macd > macd_signal:
                buy_score += 0.2
                reasons_buy.append("MACD bullish crossover")
            elif prev_macd >= prev_macd_signal and macd < macd_signal:
                sell_score += 0.2
                reasons_sell.append("MACD bearish crossover")
            elif macd > macd_signal:
                buy_score += 0.1
                reasons_buy.append("MACD above signal line")
            else:
                sell_score += 0.1
                reasons_sell.append("MACD below signal line")

        # Histogram momentum
        if _valid(macd_hist):
            prev_hist = prev.get("macd_histogram")
            if _valid(prev_hist):
                if macd_hist > 0 and macd_hist > prev_hist:
                    buy_score += 0.05
                    reasons_buy.append("MACD histogram increasing")
                elif macd_hist < 0 and macd_hist < prev_hist:
                    sell_score += 0.05
                    reasons_sell.append("MACD histogram decreasing")

        # --- 4. Bollinger Bands (weight: 0.15) ---
        bb_upper = latest.get("bb_upper")
        bb_lower = latest.get("bb_lower")
        bb_middle = latest.get("bb_middle")
        close = latest["close"]

        if _valid(bb_upper, bb_lower, bb_middle):
            if close <= bb_lower:
                buy_score += 0.15
                reasons_buy.append("Price at lower Bollinger Band (oversold)")
            elif close >= bb_upper:
                sell_score += 0.15
                reasons_sell.append("Price at upper Bollinger Band (overbought)")
            elif close < bb_middle:
                buy_score += 0.05
                reasons_buy.append("Price below BB middle")
            else:
                sell_score += 0.05
                reasons_sell.append("Price above BB middle")

        # --- 5. ADX Trend Strength (weight: 0.1) ---
        adx = latest.get("adx")
        adx_pos = latest.get("adx_pos")
        adx_neg = latest.get("adx_neg")

        if _valid(adx, adx_pos, adx_neg):
            if adx > 25:  # Strong trend
                if adx_pos > adx_neg:
                    buy_score += 0.1
                    reasons_buy.append(f"Strong uptrend (ADX={adx:.1f})")
                else:
                    sell_score += 0.1
                    reasons_sell.append(f"Strong downtrend (ADX={adx:.1f})")

        # --- 6. Stochastic (weight: 0.1) ---
        stoch_k = latest.get("stoch_k")
        stoch_d = latest.get("stoch_d")

        if _valid(stoch_k, stoch_d):
            if stoch_k < 20 and stoch_d < 20:
                buy_score += 0.1
                reasons_buy.append(f"Stochastic oversold (K={stoch_k:.1f})")
            elif stoch_k > 80 and stoch_d > 80:
                sell_score += 0.1
                reasons_sell.append(f"Stochastic overbought (K={stoch_k:.1f})")

        # --- 7. Rate of Change — Dual ROC + Composite (weight: 0.15 + conviction) ---
        roc_fast = latest.get("roc_fast")        # 9-period
        roc_medium = latest.get("roc_medium")    # 14-period
        roc_slow = latest.get("roc_slow")        # 30-period
        roc_composite = latest.get("roc_composite")
        prev_roc_fast = prev.get("roc_fast")

        # 7a. Multi-timeframe ROC alignment (weight: 0.15)
        if _valid(roc_fast, roc_medium):
            roc_slow_val = roc_slow if _valid(roc_slow) else None

            # Count how many ROC timeframes agree on direction
            bullish_count = sum(1 for v in [roc_fast, roc_medium, roc_slow_val]
                                if v is not None and v > 0)
            bearish_count = sum(1 for v in [roc_fast, roc_medium, roc_slow_val]
                                if v is not None and v < 0)
            total_roc = sum(1 for v in [roc_fast, roc_medium, roc_slow_val]
                            if v is not None)

            if bullish_count == total_roc and total_roc >= 2:
                # All timeframes bullish — strong momentum
                buy_score += 0.15
                reasons_buy.append(
                    f"ROC all bullish ({bullish_count}/{total_roc} timeframes, "
                    f"fast={roc_fast:+.2f}%, composite={roc_composite:+.2f}%)"
                )
            elif bearish_count == total_roc and total_roc >= 2:
                # All timeframes bearish — strong momentum
                sell_score += 0.15
                reasons_sell.append(
                    f"ROC all bearish ({bearish_count}/{total_roc} timeframes, "
                    f"fast={roc_fast:+.2f}%, composite={roc_composite:+.2f}%)"
                )
            elif bullish_count > bearish_count:
                buy_score += 0.07
                reasons_buy.append(
                    f"ROC leaning bullish ({bullish_count}/{total_roc}, "
                    f"fast={roc_fast:+.2f}%)"
                )
            elif bearish_count > bullish_count:
                sell_score += 0.07
                reasons_sell.append(
                    f"ROC leaning bearish ({bearish_count}/{total_roc}, "
                    f"fast={roc_fast:+.2f}%)"
                )

            # 7b. Zero-line crossover on fast ROC (entry timing bonus: 0.05)
            if _valid(prev_roc_fast):
                if prev_roc_fast <= 0 < roc_fast:
                    buy_score += 0.05
                    reasons_buy.append(
                        f"ROC fast crossed above zero ({prev_roc_fast:+.2f}% → {roc_fast:+.2f}%)"
                    )
                elif prev_roc_fast >= 0 > roc_fast:
                    sell_score += 0.05
                    reasons_sell.append(
                        f"ROC fast crossed below zero ({prev_roc_fast:+.2f}% → {roc_fast:+.2f}%)"
                    )

        # --- Calculate stop loss and take profit using ATR ---
        atr = latest.get("atr")
        if not _valid(atr) or atr == 0:
            # Fallback: use spread-based stop
            spread = latest.get("spread", 0.001)
            atr = max(spread * 10, 0.001)

        stop_distance = round(atr * 1.5, 4)  # 1.5x ATR for stop loss
        limit_distance = round(stop_distance * self.RISK_REWARD_RATIO, 4)

        # --- Final Decision ---
        total_score = buy_score + sell_score
        if total_score == 0:
            return TradeSignal(
                direction=Signal.HOLD,
                confidence=0.0,
                stop_distance=stop_distance,
                limit_distance=limit_distance,
                reasons=["No clear signals"],
                indicators=indicators,
            )

        if buy_score > sell_score:
            confidence = buy_score / (buy_score + sell_score)
            direction = Signal.BUY if confidence >= self.confidence_threshold else Signal.HOLD
            reasons = reasons_buy
        else:
            confidence = sell_score / (buy_score + sell_score)
            direction = Signal.SELL if confidence >= self.confidence_threshold else Signal.HOLD
            reasons = reasons_sell

        # --- ROC Conviction Multiplier ---
        # Boost or dampen confidence based on ROC composite alignment with
        # the chosen direction.  This rewards trades where momentum strongly
        # agrees and penalises trades where momentum diverges.
        if direction != Signal.HOLD and _valid(roc_composite):
            if direction == Signal.BUY and roc_composite > 0:
                # Momentum confirms buy — boost up to +10%
                boost = min(abs(roc_composite) / 100, 0.10)
                confidence = min(1.0, confidence + boost)
                reasons.append(f"ROC conviction boost +{boost:.0%} (composite={roc_composite:+.2f}%)")
            elif direction == Signal.SELL and roc_composite < 0:
                # Momentum confirms sell — boost up to +10%
                boost = min(abs(roc_composite) / 100, 0.10)
                confidence = min(1.0, confidence + boost)
                reasons.append(f"ROC conviction boost +{boost:.0%} (composite={roc_composite:+.2f}%)")
            else:
                # Momentum diverges from signal — dampen up to -8%
                penalty = min(abs(roc_composite) / 150, 0.08)
                confidence = max(0.0, confidence - penalty)
                reasons.append(f"ROC divergence penalty -{penalty:.0%} (composite={roc_composite:+.2f}%)")
                # Re-check threshold after penalty
                if confidence < self.confidence_threshold:
                    direction = Signal.HOLD

        if direction == Signal.HOLD:
            reasons = reasons_buy + reasons_sell
            reasons.append(
                f"Confidence too low ({confidence:.0%} < {self.confidence_threshold:.0%})"
            )

        logger.info(
            "Signal: %s (confidence=%.2f, stop=%.4f, limit=%.4f) - %s",
            direction,
            confidence,
            stop_distance,
            limit_distance,
            "; ".join(reasons),
        )

        return TradeSignal(
            direction=direction,
            confidence=confidence,
            stop_distance=stop_distance,
            limit_distance=limit_distance,
            reasons=reasons,
            indicators=indicators,
        )


def _valid(*values) -> bool:
    """Check that all values are non-None and not NaN."""
    import math

    for v in values:
        if v is None:
            return False
        try:
            if math.isnan(float(v)):
                return False
        except (ValueError, TypeError):
            return False
    return True
