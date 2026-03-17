import asyncio
import logging
from datetime import datetime, timezone
from ig_client import IGClient
from strategy import TradingStrategy, Signal, TradeSignal
from config import settings
import database as db
from sync_retry import sync_queue, SyncOp

logger = logging.getLogger(__name__)


class TradeRecord:
    def __init__(
        self,
        epic: str,
        deal_id: str,
        direction: str,
        size: float,
        open_level: float,
        stop_distance: float,
        limit_distance: float,
        signal: TradeSignal,
        opened_at: str,
        currency: str = "USD",
        market_snapshot: dict | None = None,
    ):
        self.epic = epic
        self.deal_id = deal_id
        self.direction = direction
        self.size = size
        self.open_level = open_level
        self.stop_distance = stop_distance
        self.limit_distance = limit_distance
        self.signal = signal
        self.opened_at = opened_at
        self.currency = currency
        self.market_snapshot = market_snapshot or {}
        self.status = "OPEN"
        self.pnl: float | None = None
        self.close_level: float | None = None
        self.closed_at: str | None = None
        # Compute absolute stop/limit levels
        self.stop_level: float | None = None
        self.limit_level: float | None = None
        if open_level and stop_distance:
            if direction == "BUY":
                self.stop_level = open_level - stop_distance * self._point_size(epic, market_snapshot)
                self.limit_level = open_level + limit_distance * self._point_size(epic, market_snapshot) if limit_distance else None
            else:
                self.stop_level = open_level + stop_distance * self._point_size(epic, market_snapshot)
                self.limit_level = open_level - limit_distance * self._point_size(epic, market_snapshot) if limit_distance else None

    @staticmethod
    def _point_size(epic: str, snapshot: dict | None) -> float:
        """Compute point size from scaling factor. Points / scalingFactor = raw price distance."""
        if not snapshot:
            return 0.0001  # default for forex
        scaling = snapshot.get("scalingFactor", 10000)
        return 1.0 / scaling if scaling else 0.0001

    def to_dict(self) -> dict:
        sig = self.signal.to_dict() if self.signal else {}
        return {
            "epic": self.epic,
            "dealId": self.deal_id,
            "direction": self.direction,
            "size": self.size,
            "openLevel": self.open_level,
            "stopDistance": self.stop_distance,
            "limitDistance": self.limit_distance,
            "stopLevel": self.stop_level,
            "limitLevel": self.limit_level,
            "currency": self.currency,
            "confidence": sig.get("confidence", 0),
            "signal": sig,
            "openedAt": self.opened_at,
            "status": self.status,
            "pnl": self.pnl,
            "closeLevel": self.close_level,
            "closedAt": self.closed_at,
            "scalingFactor": self.market_snapshot.get("scalingFactor", 10000) if self.market_snapshot else 10000,
        }

    def to_db_dict(self) -> dict:
        """Convert to a flat dict suitable for database storage."""
        sig = self.signal.to_dict() if self.signal else {}
        return {
            "deal_id": self.deal_id,
            "epic": self.epic,
            "direction": self.direction,
            "size": self.size,
            "open_level": self.open_level,
            "stop_distance": self.stop_distance,
            "limit_distance": self.limit_distance,
            "stop_level": self.stop_level,
            "limit_level": self.limit_level,
            "currency": self.currency,
            "confidence": sig.get("confidence", 0),
            "signal_direction": sig.get("direction", self.direction),
            "signal_reasons": sig.get("reasons", []),
            "indicators": sig.get("indicators", {}),
            "market_snapshot": self.market_snapshot,
            "status": self.status,
            "pnl": self.pnl,
            "close_level": self.close_level,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
        }


class AutoTrader:
    """Automated trading engine that analyses markets and places trades."""

    def __init__(self, client: IGClient):
        self.client = client
        self.strategy = TradingStrategy()
        self.trades: list[TradeRecord] = []
        self.market_data: dict[str, dict] = {}  # epic -> latest analysis
        self.running = False
        self._task: asyncio.Task | None = None
        self._forbidden_epics: set[str] = set()  # epics that returned 403 — skip on future cycles
        # Load persisted trades from DB
        self._load_trades_from_db()

    def _load_trades_from_db(self):
        """Load previously saved trades from the database on startup."""
        try:
            saved = db.load_trades()
            for t in saved:
                signal = TradeSignal(
                    direction=t.get("signal_direction", t["direction"]),
                    confidence=t.get("confidence", 0),
                    stop_distance=t.get("stop_distance", 0),
                    limit_distance=t.get("limit_distance", 0),
                    reasons=t.get("signal_reasons", []),
                    indicators=t.get("indicators", {}),
                )
                record = TradeRecord(
                    epic=t["epic"],
                    deal_id=t["deal_id"],
                    direction=t["direction"],
                    size=float(t.get("size", 0)),
                    open_level=float(t.get("open_level", 0)),
                    stop_distance=float(t.get("stop_distance", 0)),
                    limit_distance=float(t.get("limit_distance", 0)),
                    signal=signal,
                    opened_at=t.get("opened_at", ""),
                    currency=t.get("currency", "USD"),
                    market_snapshot=t.get("market_snapshot", {}),
                )
                record.status = t.get("status", "OPEN")
                record.pnl = t.get("pnl")
                record.close_level = t.get("close_level")
                record.closed_at = t.get("closed_at")
                record.stop_level = t.get("stop_level")
                record.limit_level = t.get("limit_level")
                self.trades.append(record)
            if saved:
                logger.info("Loaded %d trades from database", len(saved))
        except Exception as e:
            logger.error("Failed to load trades from DB: %s", e)

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("AutoTrader started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AutoTrader stopped")

    async def _run_loop(self):
        while self.running:
            try:
                await self.analyse_and_trade()
            except Exception as e:
                logger.error("Trading loop error: %s", e, exc_info=True)
            await asyncio.sleep(settings.analysis_interval_seconds)

    async def analyse_and_trade(self):
        """Run analysis on all currency pairs and execute trades."""
        open_positions = await self.client.get_open_positions()
        open_epics = {p["market"]["epic"] for p in open_positions}

        # Update existing trade records with live P&L
        self._update_trade_pnl(open_positions)

        for epic in settings.currency_pairs:
            if epic in self._forbidden_epics:
                continue  # Already confirmed no access — skip silently
            try:
                await self._analyse_pair(epic, open_epics)
            except Exception as e:
                logger.error("Error analysing %s: %s", epic, e)

    async def _analyse_pair(self, epic: str, open_epics: set):
        """Analyse a single currency pair."""
        import httpx

        # Fetch price data
        # 403 = account can't access this epic (permanent)
        # 401 = session expired (auto-reauth should have handled it, but report if not)
        try:
            prices = await self.client.get_prices(epic, resolution="HOUR", num_points=50)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 403:
                self._forbidden_epics.add(epic)
                logger.warning(
                    "403 Forbidden for %s — your account does not have access to "
                    "this market. Marked as forbidden; will not retry until removed and re-added.",
                    epic,
                )
                self.market_data[epic] = {
                    "epic": epic,
                    "instrumentName": self.market_data.get(epic, {}).get("instrumentName", epic),
                    "marketStatus": "FORBIDDEN",
                    "error": "No access — remove this market from your watchlist",
                    "lastAnalysed": datetime.now(timezone.utc).isoformat(),
                }
                return
            if status == 401:
                logger.error(
                    "401 Unauthorized for %s — session expired and re-auth failed",
                    epic,
                )
                self.market_data[epic] = {
                    "epic": epic,
                    "instrumentName": self.market_data.get(epic, {}).get("instrumentName", epic),
                    "marketStatus": "SESSION_EXPIRED",
                    "error": "Session expired — please re-login",
                    "lastAnalysed": datetime.now(timezone.utc).isoformat(),
                }
                return
            raise

        # Get market details for context
        try:
            market = await self.client.get_market_details(epic)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 401):
                logger.warning("%d on market details for %s, using empty details", e.response.status_code, epic)
                market = {}
            else:
                raise
        except Exception:
            market = {}

        # Run strategy
        signal = self.strategy.analyse(prices)

        # Store market data for the dashboard
        market_snapshot = market.get("snapshot") or {}
        instrument = market.get("instrument") or {}
        dealing_rules = market.get("dealingRules") or {}

        # Debug: log raw dealing rules for trade-size resolution
        raw_min_deal = (dealing_rules.get("minDealSize") or {})
        logger.debug(
            "Market %s: dealingRules.minDealSize=%s, instrument.lotSize=%s",
            epic, raw_min_deal, instrument.get("lotSize"),
        )
        self.market_data[epic] = {
            "epic": epic,
            "instrumentName": instrument.get("name", epic),
            "currency": (
                (instrument.get("currencies") or [{}])[0] or {}
            ).get("code", "USD") if instrument.get("currencies") else "USD",
            "bid": market_snapshot.get("bid"),
            "offer": market_snapshot.get("offer"),
            "high": market_snapshot.get("high"),
            "low": market_snapshot.get("low"),
            "change": market_snapshot.get("netChange"),
            "changePct": market_snapshot.get("percentageChange"),
            "marketStatus": market_snapshot.get("marketStatus"),
            "scalingFactor": market_snapshot.get("scalingFactor", 1),
            "minStopDistance": (dealing_rules.get("minNormalStopOrLimitDistance") or {}).get("value"),
            "minDealSize": (
                (dealing_rules.get("minDealSize") or {}).get("value")
                or instrument.get("lotSize")
            ),
            "signal": signal.to_dict(),
            "lastAnalysed": datetime.now(timezone.utc).isoformat(),
        }

        # Execute trade if signal is strong enough and no existing position
        if signal.direction != Signal.HOLD and epic not in open_epics:
            if len(open_epics) >= settings.max_open_positions:
                logger.info("Max positions reached, skipping %s", epic)
                return

            await self._execute_trade(epic, signal)

    def _convert_to_points(
        self, raw_distance: float, epic: str
    ) -> float:
        """
        Convert a raw price distance (from ATR) to IG points.

        IG expresses stop/limit distances in "points" where:
        - For most forex pairs (4 decimal): 1 point = 0.0001, so scaling = 10000
        - For JPY pairs (2 decimal): 1 point = 0.01, so scaling = 100
        - The scalingFactor from the market snapshot tells us the multiplier.

        E.g. ATR = 0.0045, scalingFactor = 10000 → 0.0045 * 10000 = 45 points
        """
        market_info = self.market_data.get(epic, {})
        scaling = market_info.get("scalingFactor", 1)

        # scalingFactor from IG is typically 1 for indices, 10000 for forex, etc.
        # If it looks like 1 (fallback/unknown), try to infer from the price
        if scaling <= 1:
            bid = market_info.get("bid")
            if bid and bid > 0:
                if bid < 10:
                    # Likely forex pair like EUR/USD (1.xxxx) → 4 decimal places
                    scaling = 10000
                elif bid < 200:
                    # Likely JPY pair (1xx.xx) → 2 decimal places
                    scaling = 100
                else:
                    # Index / commodity with larger prices
                    scaling = 1

        points = raw_distance * scaling
        return points

    def _ensure_min_stop(self, stop_points: float, epic: str) -> float:
        """Ensure stop distance meets IG minimum for the market."""
        market_info = self.market_data.get(epic, {})
        min_stop = market_info.get("minStopDistance")
        if min_stop is not None and stop_points < min_stop:
            logger.info(
                "Stop %.1f below minimum %.1f for %s, using minimum",
                stop_points,
                min_stop,
                epic,
            )
            return float(min_stop)
        return stop_points

    def _get_trade_size(self, epic: str) -> float:
        """Return the trade size for this epic.

        When use_min_trade_size is enabled, use IG's minimum deal size for the
        market.  Otherwise fall back to the user-configured default.
        """
        if settings.use_min_trade_size:
            market_info = self.market_data.get(epic, {})
            min_size = market_info.get("minDealSize")
            logger.debug(
                "use_min_trade_size=ON for %s — minDealSize from market_data: %s",
                epic, min_size,
            )
            if min_size is not None:
                try:
                    val = float(min_size)
                    if val > 0:
                        logger.info(
                            "Using IG minimum deal size %.2f for %s (toggle ON)",
                            val, epic,
                        )
                        return val
                except (ValueError, TypeError):
                    pass
            # Fallback if IG didn't provide a value — use a safe minimum
            fallback = min(0.5, settings.default_trade_size)
            logger.warning(
                "minDealSize unavailable for %s, using fallback %.2f",
                epic, fallback,
            )
            return fallback
        return settings.default_trade_size

    async def _execute_trade(self, epic: str, signal: TradeSignal):
        """Execute a trade based on the signal."""
        market_info = self.market_data.get(epic, {})
        currency = market_info.get("currency", "USD")
        trade_size = self._get_trade_size(epic)

        # Convert raw ATR-based distances to IG points
        stop_points = self._convert_to_points(signal.stop_distance, epic)
        limit_points = self._convert_to_points(signal.limit_distance, epic)

        # Enforce minimum stop distance
        stop_points = self._ensure_min_stop(stop_points, epic)

        # Limit must be at least as large as stop (maintain risk/reward)
        if limit_points < stop_points:
            limit_points = stop_points * 2.0

        # Round to whole numbers — IG wants integer-ish point values
        stop_points = round(stop_points, 1)
        limit_points = round(limit_points, 1)

        # Safety: skip if distances are nonsensical
        if stop_points <= 0 or limit_points <= 0:
            logger.warning(
                "Invalid stop/limit for %s: stop=%.1f, limit=%.1f — skipping",
                epic, stop_points, limit_points,
            )
            return

        logger.info(
            "Placing %s on %s: size=%.2f, stop=%.1f pts, limit=%.1f pts (raw ATR stop=%.6f, limit=%.6f)",
            signal.direction,
            epic,
            trade_size,
            stop_points,
            limit_points,
            signal.stop_distance,
            signal.limit_distance,
        )

        try:
            confirmation = await self.client.open_position(
                epic=epic,
                direction=signal.direction,
                size=trade_size,
                stop_distance=stop_points,
                limit_distance=limit_points,
                currency_code=currency,
            )

            if confirmation.get("dealStatus") == "ACCEPTED":
                trade = TradeRecord(
                    epic=epic,
                    deal_id=confirmation["dealId"],
                    direction=signal.direction,
                    size=trade_size,
                    open_level=confirmation.get("level", 0),
                    stop_distance=stop_points,
                    limit_distance=limit_points,
                    signal=signal,
                    opened_at=datetime.now(timezone.utc).isoformat(),
                    currency=currency,
                    market_snapshot=market_info,
                )
                self.trades.append(trade)
                # Persist to database (with retry on failure)
                trade_data = trade.to_db_dict()
                try:
                    db.save_trade(trade_data)
                except Exception as db_err:
                    logger.error("Failed to save trade to DB: %s — queued for retry", db_err)
                    sync_queue.enqueue(SyncOp.SAVE_TRADE, trade_data, str(db_err))
                logger.info(
                    "Opened %s %s at %s (stop=%.1f pts, limit=%.1f pts)",
                    signal.direction,
                    epic,
                    confirmation.get("level"),
                    stop_points,
                    limit_points,
                )
            else:
                reason = confirmation.get("reason", "Unknown")
                logger.warning("Trade rejected for %s: %s", epic, reason)

        except Exception as e:
            logger.error("Failed to execute trade for %s: %s", epic, e)

    def _update_trade_pnl(self, open_positions: list[dict]):
        """Update P&L for open trades from live position data.

        IG's positions API v2 does NOT return a 'profit' field directly.
        We compute P&L from the live bid/offer versus the open level.
        """
        pos_map = {}
        for p in open_positions:
            pos = p.get("position") or {}
            mkt = p.get("market") or {}
            deal_id = pos.get("dealId")
            if not deal_id:
                continue

            direction = pos.get("direction", "BUY")
            open_level = pos.get("level") or 0
            size = pos.get("size") or pos.get("dealSize") or 0
            bid = mkt.get("bid")
            offer = mkt.get("offer")

            # Compute P&L: BUY profits when bid rises above open level
            #               SELL profits when offer drops below open level
            pnl = None
            if open_level and size:
                if direction == "BUY" and bid is not None:
                    pnl = round((bid - open_level) * float(size), 2)
                elif direction == "SELL" and offer is not None:
                    pnl = round((open_level - offer) * float(size), 2)

            pos_map[deal_id] = {
                "pnl": pnl,
                "level": open_level,
                "bid": bid,
                "offer": offer,
                "stop_level": pos.get("stopLevel"),
                "limit_level": pos.get("limitLevel"),
            }

        for trade in self.trades:
            if trade.status == "OPEN":
                if trade.deal_id in pos_map:
                    info = pos_map[trade.deal_id]
                    new_pnl = info.get("pnl")
                    trade.pnl = new_pnl
                    # Also update stop/limit levels from live data
                    if info.get("stop_level") is not None:
                        trade.stop_level = info["stop_level"]
                    if info.get("limit_level") is not None:
                        trade.limit_level = info["limit_level"]
                    # Persist P&L update (with retry on failure)
                    try:
                        db.update_trade_pnl(trade.deal_id, new_pnl)
                    except Exception as e:
                        sync_queue.enqueue(SyncOp.UPDATE_PNL, {
                            "deal_id": trade.deal_id,
                            "pnl": new_pnl,
                        }, str(e))
                else:
                    # Position closed (hit SL/TP or manual close)
                    trade.status = "CLOSED"
                    trade.closed_at = datetime.now(timezone.utc).isoformat()
                    # Persist close to DB (with retry on failure)
                    close_payload = {
                        "deal_id": trade.deal_id,
                        "status": "CLOSED",
                        "pnl": trade.pnl,
                        "close_level": trade.close_level,
                        "closed_at": trade.closed_at,
                    }
                    try:
                        db.update_trade_status(
                            trade.deal_id, "CLOSED",
                            pnl=trade.pnl,
                            close_level=trade.close_level,
                            closed_at=trade.closed_at,
                        )
                    except Exception as e:
                        logger.error("Failed to update trade %s in DB: %s — queued for retry", trade.deal_id, e)
                        sync_queue.enqueue(SyncOp.UPDATE_STATUS, close_payload, str(e))

    async def load_open_positions(self):
        """Fetch open positions from IG and merge into self.trades so they
        appear on the dashboard even after a server restart / page refresh."""
        try:
            positions = await self.client.get_open_positions()
        except Exception as e:
            logger.error("Failed to fetch open positions: %s", e)
            return

        existing_deal_ids = {t.deal_id for t in self.trades}

        for p in positions:
            pos = p.get("position") or {}
            market = p.get("market") or {}
            deal_id = pos.get("dealId")
            if not deal_id or deal_id in existing_deal_ids:
                continue  # already tracked

            epic = market.get("epic", "")
            direction = pos.get("direction", "BUY")
            size = pos.get("size") or pos.get("dealSize") or 0
            open_level = pos.get("level") or pos.get("openLevel") or 0
            stop_level = pos.get("stopLevel")
            limit_level = pos.get("limitLevel")
            currency = pos.get("currency", "USD")
            created = pos.get("createdDateUTC") or pos.get("createdDate") or ""
            bid = market.get("bid")
            offer = market.get("offer")

            # Check DB for previously saved trade data (may have real confidence/indicators)
            db_trade = None
            try:
                db_trade = db.get_trade_by_deal_id(deal_id)
            except Exception:
                pass

            # Calculate stop/limit distances from absolute levels
            scaling = market.get("scalingFactor", 10000) or 10000
            stop_dist = abs(open_level - stop_level) * scaling if stop_level and open_level else 0
            limit_dist = abs(limit_level - open_level) * scaling if limit_level and open_level else 0

            if db_trade and db_trade.get("confidence"):
                # Restore the real signal from DB
                signal = TradeSignal(
                    direction=db_trade.get("signal_direction", direction),
                    confidence=db_trade.get("confidence", 0),
                    stop_distance=db_trade.get("stop_distance", stop_dist),
                    limit_distance=db_trade.get("limit_distance", limit_dist),
                    indicators=db_trade.get("indicators", {}),
                    reasons=db_trade.get("signal_reasons", []),
                )
                stop_dist = db_trade.get("stop_distance", stop_dist)
                limit_dist = db_trade.get("limit_distance", limit_dist)
            else:
                # Build a minimal signal placeholder
                signal = TradeSignal(
                    direction=direction,
                    confidence=0.0,
                    stop_distance=stop_dist,
                    limit_distance=limit_dist,
                    indicators={},
                    reasons=["Loaded from IG open positions"],
                )

            # Compute P&L from live bid/offer
            pnl = None
            if open_level and size:
                if direction == "BUY" and bid is not None:
                    pnl = round((bid - float(open_level)) * float(size), 2)
                elif direction == "SELL" and offer is not None:
                    pnl = round((float(open_level) - offer) * float(size), 2)

            market_snapshot = db_trade.get("market_snapshot", {}) if db_trade else {}

            trade = TradeRecord(
                epic=epic,
                deal_id=deal_id,
                direction=direction,
                size=float(size),
                open_level=float(open_level),
                stop_distance=round(float(stop_dist), 1),
                limit_distance=round(float(limit_dist), 1),
                signal=signal,
                opened_at=db_trade.get("opened_at", created) if db_trade else created,
                currency=currency,
                market_snapshot=market_snapshot,
            )
            trade.pnl = pnl
            trade.stop_level = stop_level
            trade.limit_level = limit_level
            self.trades.append(trade)
            existing_deal_ids.add(deal_id)

            # Persist to DB (won't overwrite existing confidence/indicators thanks to ON CONFLICT)
            trade_data = trade.to_db_dict()
            try:
                db.save_trade(trade_data)
            except Exception as e:
                sync_queue.enqueue(SyncOp.SAVE_TRADE, trade_data, str(e))

            logger.info("Loaded existing position: %s %s %s @ %.5f pnl=%.2f (deal %s)",
                        direction, size, epic, open_level, pnl or 0, deal_id)

    def get_state(self) -> dict:
        return {
            "running": self.running,
            "trades": [t.to_dict() for t in self.trades],
            "markets": self.market_data,
            "openTradeCount": sum(1 for t in self.trades if t.status == "OPEN"),
            "closedTradeCount": sum(1 for t in self.trades if t.status == "CLOSED"),
            "forbiddenEpics": list(self._forbidden_epics),
            "syncRetry": sync_queue.get_status(),
        }
