"""
Trading Strategy — Multi-indicator weighted scoring system.

Indicators used and their max weights:
  1. EMA Crossover (trend direction)         — 0.25  (0.20 crossover + 0.05 EMA50)
  2. MACD (trend confirmation)               — 0.25  (0.20 crossover + 0.05 histogram)
  3. Bollinger Bands (volatility/mean rev.)  — 0.05
  4. Directional Movement DI+/DI-/DX         — 0.15
  5. KDJ (momentum overbought/oversold + J)  — 0.15
  6. Stochastic (classic overbought/oversold) — 0.05
  7. ROC multi-timeframe (momentum)           — 0.30  (0.25 alignment + 0.05 zero-cross)
                                        Total ≈ 1.20  (but both sides compete)

Counter-trend checks (prevent lagging-indicator echo chamber):
  8a. Candle direction — latest candle contradicts signal → +0.10 to other side
  8b. MACD histogram deceleration — 3 declining bars → +0.08 to other side
  8c. Price-MACD divergence — higher high + lower MACD → +0.10 to other side

Confidence = winning_side / (buy_score + sell_score)  → 0..1
Then ROC conviction multiplier boosts/dampens ±10%.
Trend exhaustion cap: if losing side < 5% of total, confidence capped at 82%.
Trade placed only if confidence ≥ min_confidence setting.
"""
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
            "confidence": round(self.confidence, 4),
            "stop_distance": round(self.stop_distance, 6),
            "limit_distance": round(self.limit_distance, 6),
            "reasons": self.reasons,
            "indicators": self.indicators,
        }


class TradingStrategy:
    """
    Multi-indicator strategy combining:
    - EMA crossover (trend)
    - MACD (trend confirmation)
    - Bollinger Bands (volatility/mean reversion)
    - Directional Movement DI+/DI-/DX (trend direction + strength)
    - KDJ (momentum/overbought/oversold with J-line)
    - Stochastic (overbought/oversold)
    - Rate of Change / ROC (multi-timeframe momentum + conviction multiplier)
    - ATR (stop loss/take profit sizing)
    """

    RISK_REWARD_RATIO = 2.0  # Target profit = 2x risk

    @property
    def confidence_threshold(self) -> float:
        """Minimum confidence to trigger a trade — read from live settings."""
        return settings.min_confidence

    def analyse(self, prices_data: dict, roc_period: int = 20) -> TradeSignal:
        """Analyse price data and return a trade signal.

        Args:
            prices_data: IG price API response
            roc_period: Primary ROC lookback period (configurable per epic)
        """
        df = compute_indicators(prices_data, roc_period=roc_period)

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

        # ─── 1. EMA Crossover (weight: 0.20 crossover + 0.05 EMA50) ───
        ema_9 = latest.get("ema_9")
        ema_21 = latest.get("ema_21")
        ema_50 = latest.get("ema_50")
        prev_ema_9 = prev.get("ema_9")
        prev_ema_21 = prev.get("ema_21")

        if _valid(ema_9, ema_21, prev_ema_9, prev_ema_21):
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

        if _valid(ema_50):
            close = latest["close"]
            if close > ema_50:
                buy_score += 0.05
                reasons_buy.append("Price above EMA 50")
            else:
                sell_score += 0.05
                reasons_sell.append("Price below EMA 50")

        # ─── 2. MACD (weight: 0.20 crossover + 0.05 histogram) ────────
        macd = latest.get("macd")
        macd_signal = latest.get("macd_signal")
        macd_hist = latest.get("macd_histogram")
        prev_macd = prev.get("macd")
        prev_macd_signal = prev.get("macd_signal")

        if _valid(macd, macd_signal, prev_macd, prev_macd_signal):
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

        if _valid(macd_hist):
            prev_hist = prev.get("macd_histogram")
            if _valid(prev_hist):
                if macd_hist > 0 and macd_hist > prev_hist:
                    buy_score += 0.05
                    reasons_buy.append("MACD histogram increasing")
                elif macd_hist < 0 and macd_hist < prev_hist:
                    sell_score += 0.05
                    reasons_sell.append("MACD histogram decreasing")

        # ─── 3. Bollinger Bands (weight: 0.05) ────────────────────────
        bb_upper = latest.get("bb_upper")
        bb_lower = latest.get("bb_lower")
        bb_middle = latest.get("bb_middle")
        close = latest["close"]

        if _valid(bb_upper, bb_lower, bb_middle):
            if close <= bb_lower:
                buy_score += 0.05
                reasons_buy.append("Price at lower Bollinger Band (oversold)")
            elif close >= bb_upper:
                sell_score += 0.05
                reasons_sell.append("Price at upper Bollinger Band (overbought)")
            elif close < bb_middle:
                buy_score += 0.02
                reasons_buy.append("Price below BB middle")
            else:
                sell_score += 0.02
                reasons_sell.append("Price above BB middle")

        # ─── 4. Directional Movement DI+/DI-/DX (weight: 0.15) ───────
        di_plus = latest.get("di_plus")
        di_minus = latest.get("di_minus")
        dx = latest.get("dx")
        prev_di_plus = prev.get("di_plus")
        prev_di_minus = prev.get("di_minus")

        if _valid(di_plus, di_minus, dx):
            if dx > 20:  # Trending market (DX > 20 means directional)
                if di_plus > di_minus:
                    buy_score += 0.15
                    reasons_buy.append(
                        f"DI+ > DI- in trending market (DI+={di_plus:.1f}, "
                        f"DI-={di_minus:.1f}, DX={dx:.1f})"
                    )
                else:
                    sell_score += 0.15
                    reasons_sell.append(
                        f"DI- > DI+ in trending market (DI+={di_plus:.1f}, "
                        f"DI-={di_minus:.1f}, DX={dx:.1f})"
                    )
            elif _valid(prev_di_plus, prev_di_minus):
                # DI crossover even in weak trend
                if prev_di_plus <= prev_di_minus and di_plus > di_minus:
                    buy_score += 0.08
                    reasons_buy.append(
                        f"DI+ crossed above DI- ({di_plus:.1f} > {di_minus:.1f})"
                    )
                elif prev_di_plus >= prev_di_minus and di_plus < di_minus:
                    sell_score += 0.08
                    reasons_sell.append(
                        f"DI- crossed above DI+ ({di_minus:.1f} > {di_plus:.1f})"
                    )

        # ─── 5. KDJ Indicator (weight: 0.15) ─────────────────────────
        kdj_k = latest.get("kdj_k")
        kdj_d = latest.get("kdj_d")
        kdj_j = latest.get("kdj_j")
        prev_kdj_k = prev.get("kdj_k")
        prev_kdj_d = prev.get("kdj_d")

        if _valid(kdj_k, kdj_d, kdj_j):
            # J-line extremes (J is more sensitive than K/D)
            if kdj_j < 0:
                buy_score += 0.10
                reasons_buy.append(f"KDJ J-line strongly oversold (J={kdj_j:.1f})")
            elif kdj_j > 100:
                sell_score += 0.10
                reasons_sell.append(f"KDJ J-line strongly overbought (J={kdj_j:.1f})")
            elif kdj_j < 20:
                buy_score += 0.05
                reasons_buy.append(f"KDJ J-line oversold (J={kdj_j:.1f})")
            elif kdj_j > 80:
                sell_score += 0.05
                reasons_sell.append(f"KDJ J-line overbought (J={kdj_j:.1f})")

            # K/D crossover (golden/death cross of KDJ)
            if _valid(prev_kdj_k, prev_kdj_d):
                if prev_kdj_k <= prev_kdj_d and kdj_k > kdj_d:
                    buy_score += 0.05
                    reasons_buy.append(
                        f"KDJ golden cross (K={kdj_k:.1f} > D={kdj_d:.1f})"
                    )
                elif prev_kdj_k >= prev_kdj_d and kdj_k < kdj_d:
                    sell_score += 0.05
                    reasons_sell.append(
                        f"KDJ death cross (K={kdj_k:.1f} < D={kdj_d:.1f})"
                    )

        # ─── 6. Stochastic Classic (weight: 0.05) ────────────────────
        stoch_k = latest.get("stoch_k")
        stoch_d = latest.get("stoch_d")

        if _valid(stoch_k, stoch_d):
            if stoch_k < 20 and stoch_d < 20:
                buy_score += 0.05
                reasons_buy.append(f"Stochastic oversold (K={stoch_k:.1f})")
            elif stoch_k > 80 and stoch_d > 80:
                sell_score += 0.05
                reasons_sell.append(f"Stochastic overbought (K={stoch_k:.1f})")

        # ─── 7. Rate of Change — Multi-timeframe (0.25 + 0.05 = 0.30) ─
        roc_fast = latest.get("roc_fast")
        roc_medium = latest.get("roc_medium")
        roc_slow = latest.get("roc_slow")
        roc_composite = latest.get("roc_composite")
        prev_roc_fast = prev.get("roc_fast")

        # 7a. Multi-timeframe ROC alignment (weight: 0.25)
        if _valid(roc_fast, roc_medium):
            roc_slow_val = roc_slow if _valid(roc_slow) else None

            bullish_count = sum(1 for v in [roc_fast, roc_medium, roc_slow_val]
                                if v is not None and v > 0)
            bearish_count = sum(1 for v in [roc_fast, roc_medium, roc_slow_val]
                                if v is not None and v < 0)
            total_roc = sum(1 for v in [roc_fast, roc_medium, roc_slow_val]
                            if v is not None)

            if bullish_count == total_roc and total_roc >= 2:
                buy_score += 0.25
                reasons_buy.append(
                    f"ROC all bullish ({bullish_count}/{total_roc} TFs, "
                    f"fast={roc_fast:+.2f}%, composite={roc_composite:+.2f}%)"
                )
            elif bearish_count == total_roc and total_roc >= 2:
                sell_score += 0.25
                reasons_sell.append(
                    f"ROC all bearish ({bearish_count}/{total_roc} TFs, "
                    f"fast={roc_fast:+.2f}%, composite={roc_composite:+.2f}%)"
                )
            elif bullish_count > bearish_count:
                buy_score += 0.12
                reasons_buy.append(
                    f"ROC leaning bullish ({bullish_count}/{total_roc}, "
                    f"fast={roc_fast:+.2f}%)"
                )
            elif bearish_count > bullish_count:
                sell_score += 0.12
                reasons_sell.append(
                    f"ROC leaning bearish ({bearish_count}/{total_roc}, "
                    f"fast={roc_fast:+.2f}%)"
                )

            # 7b. Zero-line crossover on fast ROC (entry timing: 0.05)
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

        # ═══════════════════════════════════════════════════════════════
        # 8. COUNTER-TREND CHECKS (penalties that reduce overconfidence)
        #    These detect when lagging indicators are stale / trend is
        #    exhausting, preventing the "echo chamber" problem.
        # ═══════════════════════════════════════════════════════════════

        # 8a. Candle direction check — if latest candle closed lower than
        #     open but all indicators say BUY, apply a penalty (and vice
        #     versa). This is the most immediate price-action signal.
        candle_open = latest.get("open")
        candle_close = latest.get("close")
        if _valid(candle_open, candle_close) and candle_open != 0:
            candle_bearish = candle_close < candle_open
            candle_bullish = candle_close > candle_open
            # Penalty: current candle contradicts the dominant signal
            if candle_bearish and buy_score > sell_score:
                penalty = 0.10
                sell_score += penalty
                reasons_sell.append(
                    f"Latest candle is bearish (O={candle_open:.5f} → C={candle_close:.5f})"
                )
            elif candle_bullish and sell_score > buy_score:
                penalty = 0.10
                buy_score += penalty
                reasons_buy.append(
                    f"Latest candle is bullish (O={candle_open:.5f} → C={candle_close:.5f})"
                )

        # 8b. MACD Histogram divergence — if MACD histogram is declining
        #     (losing momentum) even though MACD is still above signal,
        #     the trend is weakening.  Check last 3 bars for deceleration.
        if len(df) >= 4:
            hist_vals = df["macd_histogram"].iloc[-3:].tolist()
            if all(_valid(h) for h in hist_vals):
                if hist_vals[-1] > 0 and hist_vals[-1] < hist_vals[-2] < hist_vals[-3]:
                    # Bullish momentum decelerating (3 declining positive bars)
                    sell_score += 0.08
                    reasons_sell.append(
                        f"MACD histogram declining (momentum fading: "
                        f"{hist_vals[-3]:.4f} → {hist_vals[-2]:.4f} → {hist_vals[-1]:.4f})"
                    )
                elif hist_vals[-1] < 0 and hist_vals[-1] > hist_vals[-2] > hist_vals[-3]:
                    # Bearish momentum decelerating (3 rising negative bars)
                    buy_score += 0.08
                    reasons_buy.append(
                        f"MACD histogram recovering (selling fading: "
                        f"{hist_vals[-3]:.4f} → {hist_vals[-2]:.4f} → {hist_vals[-1]:.4f})"
                    )

        # 8c. Price-MACD divergence — price making higher high but MACD
        #     making lower high = bearish divergence (and vice versa).
        #     Look at last 10 bars for swing highs/lows.
        if len(df) >= 10:
            recent = df.iloc[-10:]
            price_high_idx = recent["close"].idxmax()
            price_low_idx = recent["close"].idxmin()
            first_half = df.iloc[-10:-5]
            second_half = df.iloc[-5:]

            if not first_half.empty and not second_half.empty:
                fh_price_high = first_half["close"].max()
                sh_price_high = second_half["close"].max()
                fh_macd_high = first_half["macd"].max() if "macd" in first_half else None
                sh_macd_high = second_half["macd"].max() if "macd" in second_half else None

                fh_price_low = first_half["close"].min()
                sh_price_low = second_half["close"].min()
                fh_macd_low = first_half["macd"].min() if "macd" in first_half else None
                sh_macd_low = second_half["macd"].min() if "macd" in second_half else None

                # Bearish divergence: higher price high + lower MACD high
                if (_valid(fh_macd_high, sh_macd_high)
                        and sh_price_high > fh_price_high
                        and sh_macd_high < fh_macd_high):
                    sell_score += 0.10
                    reasons_sell.append(
                        "Bearish divergence: price higher high but MACD lower high"
                    )

                # Bullish divergence: lower price low + higher MACD low
                if (_valid(fh_macd_low, sh_macd_low)
                        and sh_price_low < fh_price_low
                        and sh_macd_low > fh_macd_low):
                    buy_score += 0.10
                    reasons_buy.append(
                        "Bullish divergence: price lower low but MACD higher low"
                    )

        # ═══════════════════════════════════════════════════════════════
        # STOP LOSS / TAKE PROFIT (ATR-based)
        # ═══════════════════════════════════════════════════════════════
        atr = latest.get("atr")
        if not _valid(atr) or atr == 0:
            spread = latest.get("spread", 0.001)
            atr = max(spread * 10, 0.001)

        stop_distance = round(atr * 1.5, 4)
        limit_distance = round(stop_distance * self.RISK_REWARD_RATIO, 4)

        # ═══════════════════════════════════════════════════════════════
        # FINAL DECISION
        # ═══════════════════════════════════════════════════════════════
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

        # ── ROC Conviction Multiplier ──
        if direction != Signal.HOLD and _valid(roc_composite):
            if direction == Signal.BUY and roc_composite > 0:
                boost = min(abs(roc_composite) / 100, 0.10)
                confidence = min(1.0, confidence + boost)
                reasons.append(f"ROC conviction boost +{boost:.0%} (composite={roc_composite:+.2f}%)")
            elif direction == Signal.SELL and roc_composite < 0:
                boost = min(abs(roc_composite) / 100, 0.10)
                confidence = min(1.0, confidence + boost)
                reasons.append(f"ROC conviction boost +{boost:.0%} (composite={roc_composite:+.2f}%)")
            else:
                penalty = min(abs(roc_composite) / 150, 0.08)
                confidence = max(0.0, confidence - penalty)
                reasons.append(f"ROC divergence penalty -{penalty:.0%} (composite={roc_composite:+.2f}%)")
                if confidence < self.confidence_threshold:
                    direction = Signal.HOLD

        # ── Trend Exhaustion Cap ──
        # When the losing side has almost zero score, it means ALL
        # lagging indicators agree.  This is suspicious — cap confidence
        # because unanimous agreement from lagging indicators often
        # signals the END of a trend, not the beginning.
        if direction != Signal.HOLD:
            losing_score = sell_score if direction == Signal.BUY else buy_score
            if total_score > 0 and (losing_score / total_score) < 0.05:
                cap = 0.82  # Max confidence when no counter-signals exist
                if confidence > cap:
                    reasons.append(
                        f"Trend exhaustion cap: all lagging indicators agree "
                        f"(conf {confidence:.0%} → {cap:.0%})"
                    )
                    confidence = cap

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
