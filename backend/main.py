import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import settings
from ig_client import IGClient
from trader import AutoTrader
from sync_retry import sync_queue
import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global instances
ig_client: IGClient | None = None
auto_trader: AutoTrader | None = None
ws_clients: set[WebSocket] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ig_client, auto_trader

    # Initialize database
    db.init_db()

    # Load saved bot config
    saved_config = db.load_bot_config()
    if saved_config:
        settings.default_trade_size = saved_config["trade_size"]
        settings.max_open_positions = saved_config["max_positions"]
        settings.analysis_interval_seconds = saved_config["analysis_interval"]
        settings.min_confidence = saved_config.get("min_confidence", 0.55)
        settings.use_min_trade_size = saved_config.get("use_min_trade_size", False)
        logger.info("Loaded bot config from DB: size=%.1f, max=%d, interval=%ds, minConf=%.0f%%, useMinSize=%s",
                     saved_config["trade_size"], saved_config["max_positions"],
                     saved_config["analysis_interval"], settings.min_confidence * 100,
                     settings.use_min_trade_size)

    # Load saved watchlist (replaces hardcoded defaults if DB has data)
    saved_watchlist = db.load_watchlist()
    if saved_watchlist:
        settings.currency_pairs = saved_watchlist
        logger.info("Loaded watchlist from DB: %d pairs", len(saved_watchlist))

    # Load saved credentials and try auto-login
    saved_creds = db.load_credentials()
    if saved_creds:
        api_key = saved_creds["api_key"] or settings.ig_api_key
        api_url = saved_creds["api_url"] or settings.ig_api_url
        ig_client = IGClient(api_key=api_key, base_url=api_url)
        try:
            await ig_client.login(saved_creds["username"], saved_creds["password"])
            logger.info("Auto-login successful for user: %s", saved_creds["username"])
        except Exception as e:
            logger.warning("Auto-login failed (saved credentials may be expired): %s", e)
    else:
        ig_client = IGClient(api_key=settings.ig_api_key, base_url=settings.ig_api_url)

    auto_trader = AutoTrader(ig_client)

    # Start background tasks
    broadcast_task = asyncio.create_task(broadcast_loop())
    sync_queue.start()
    yield

    # Cleanup
    broadcast_task.cancel()
    sync_queue.stop()
    if auto_trader.running:
        await auto_trader.stop()
    await ig_client.close()


app = FastAPI(title="IG Trading Bot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- REST Endpoints ---


@app.post("/api/auth/login")
async def login(body: dict):
    """Login to IG API with username and password."""
    username = body.get("username", settings.ig_username)
    password = body.get("password", settings.ig_password)
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    try:
        result = await ig_client.login(username, password)
    except Exception as e:
        raise HTTPException(401, f"Login failed: {e}")

    # Save credentials to DB (don't let DB errors break the login response)
    try:
        db.save_credentials(
            username=username,
            password=password,
            api_key=ig_client.api_key,
            api_url=ig_client.base_url,
        )
    except Exception as e:
        logger.error("Failed to save credentials to DB: %s", e)

    return {
        "status": "ok",
        "accountId": ig_client.account_id,
        "lightstreamerEndpoint": ig_client.lightstreamer_endpoint,
    }


@app.get("/api/auth/status")
async def auth_status():
    return {
        "authenticated": ig_client.is_authenticated if ig_client else False,
        "hasSavedCredentials": db.load_credentials() is not None,
        "canAutoReauth": ig_client.can_reauth if ig_client else False,
        "accountId": ig_client.account_id if ig_client else None,
    }


@app.post("/api/auth/logout")
async def logout():
    """Clear saved credentials and session."""
    db.clear_credentials()
    # Reset the client session tokens and saved credentials
    if ig_client:
        ig_client.cst = None
        ig_client.security_token = None
        ig_client._username = None
        ig_client._password = None
    return {"status": "ok"}


@app.post("/api/trader/start")
async def start_trader():
    if not ig_client or not ig_client.is_authenticated:
        raise HTTPException(401, "Not authenticated. Login first.")
    await auto_trader.start()
    return {"status": "started"}


@app.post("/api/trader/stop")
async def stop_trader():
    await auto_trader.stop()
    return {"status": "stopped"}


@app.get("/api/trader/state")
async def trader_state():
    if not auto_trader:
        return {"running": False, "trades": [], "markets": {}}
    # Load any open positions from IG that aren't tracked yet
    if ig_client and ig_client.is_authenticated:
        await auto_trader.load_open_positions()
    return auto_trader.get_state()


@app.post("/api/trader/analyse")
async def trigger_analysis():
    """Manually trigger analysis cycle."""
    if not ig_client or not ig_client.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    await auto_trader.analyse_and_trade()
    return auto_trader.get_state()


@app.get("/api/positions")
async def get_positions():
    if not ig_client or not ig_client.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    positions = await ig_client.get_open_positions()
    return {"positions": positions}


@app.get("/api/markets/{epic}")
async def get_market(epic: str):
    if not ig_client or not ig_client.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    details = await ig_client.get_market_details(epic)
    return details


@app.get("/api/markets/{epic}/prices")
async def get_market_prices(epic: str, resolution: str = "HOUR", points: int = 50):
    if not ig_client or not ig_client.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    prices = await ig_client.get_prices(epic, resolution, points)
    return prices


@app.get("/api/accounts")
async def get_accounts():
    if not ig_client or not ig_client.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    accounts = await ig_client.get_accounts()
    return {"accounts": accounts}


@app.get("/api/history")
async def get_activity():
    if not ig_client or not ig_client.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    activities = await ig_client.get_activity_history()
    return {"activities": activities}


@app.get("/api/sync/status")
async def get_sync_status():
    """Get the current sync retry queue status."""
    return sync_queue.get_status()


@app.post("/api/sync/retry-dead")
async def retry_dead_letters():
    """Move all dead-letter items back to the retry queue."""
    count = sync_queue.retry_dead()
    return {"status": "ok", "requeued": count}


@app.get("/api/trades/history")
async def get_trade_history():
    """Get all closed trades from the database."""
    trades = db.load_trades(status="CLOSED")
    return {"trades": trades}


@app.get("/api/trades/all")
async def get_all_trades():
    """Get all trades (open and closed) from the database."""
    trades = db.load_trades()
    return {"trades": trades}


@app.get("/api/trades/{deal_id}")
async def get_trade_detail(deal_id: str):
    """Get detailed trade data including indicators and market snapshot."""
    trade = db.get_trade_by_deal_id(deal_id)
    if not trade:
        raise HTTPException(404, "Trade not found")
    return trade


@app.get("/api/config")
async def get_config():
    return {
        "currencyPairs": settings.currency_pairs,
        "tradeSize": settings.default_trade_size,
        "maxPositions": settings.max_open_positions,
        "analysisInterval": settings.analysis_interval_seconds,
        "minConfidence": settings.min_confidence,
        "useMinTradeSize": settings.use_min_trade_size,
        "syncRetry": sync_queue.get_status(),
    }


@app.post("/api/config")
async def update_config(body: dict):
    if "tradeSize" in body:
        settings.default_trade_size = float(body["tradeSize"])
    if "maxPositions" in body:
        settings.max_open_positions = int(body["maxPositions"])
    if "analysisInterval" in body:
        settings.analysis_interval_seconds = int(body["analysisInterval"])
    if "minConfidence" in body:
        val = float(body["minConfidence"])
        # Clamp between 0.1 and 1.0
        settings.min_confidence = max(0.1, min(1.0, val))
    if "useMinTradeSize" in body:
        settings.use_min_trade_size = bool(body["useMinTradeSize"])
    # Persist to DB
    db.save_bot_config(
        trade_size=settings.default_trade_size,
        max_positions=settings.max_open_positions,
        analysis_interval=settings.analysis_interval_seconds,
        min_confidence=settings.min_confidence,
        use_min_trade_size=settings.use_min_trade_size,
    )
    # Ensure sync retry queue is running (may have been stopped or never started)
    sync_queue.start()
    # If user explicitly asked to flush pending retries
    if body.get("flushSyncQueue"):
        sync_queue.flush_now()
    return {"status": "updated", "syncRetry": sync_queue.get_status()}


# --- Market Search & Watchlist Management ---


def _extract_contract_type(epic: str) -> str:
    """Extract the contract type from an IG epic.

    e.g. CS.D.EURUSD.CFD.IP → CFD
         CS.D.EURUSD.MINI.IP → MINI
         CS.D.EURUSD.TODAY.IP → TODAY
    """
    parts = epic.upper().split(".")
    if len(parts) >= 4:
        return parts[-2]  # second-to-last segment
    return ""


# Contract types sorted by demo-account accessibility (best first)
_CONTRACT_RANK = {"CFD": 0, "TODAY": 1, "MINI": 2}


@app.get("/api/search")
async def search_markets(q: str = ""):
    """Search IG markets by keyword. Returns matching instruments."""
    if not ig_client or not ig_client.is_authenticated:
        raise HTTPException(401, "Not authenticated")
    if not q or len(q.strip()) < 2:
        raise HTTPException(400, "Search query must be at least 2 characters")
    try:
        results = await ig_client.search_markets(q.strip())
        # Annotate each result with watchlist status and contract type
        watched_set = set(settings.currency_pairs)
        forbidden_set = auto_trader._forbidden_epics if auto_trader else set()
        for r in results:
            epic = r.get("epic", "")
            r["watched"] = epic in watched_set
            ct = _extract_contract_type(epic)
            r["contractType"] = ct
            # Warn if this contract type is known to be restricted on demo
            if epic in forbidden_set:
                r["demoRestricted"] = True
            elif ct == "MINI":
                r["demoWarning"] = "MINI contracts may not be available on demo accounts"
        # Sort: CFD first, then by instrument name
        results.sort(
            key=lambda r: (
                _CONTRACT_RANK.get(r.get("contractType", ""), 5),
                r.get("instrumentName", ""),
            )
        )
        return {"markets": results}
    except Exception as e:
        logger.error("Market search failed: %s", e)
        raise HTTPException(500, f"Search failed: {e}")


@app.get("/api/watchlist")
async def get_watchlist():
    """Return the current currency pairs watchlist."""
    return {"pairs": settings.currency_pairs}


@app.post("/api/watchlist/add")
async def add_to_watchlist(body: dict):
    """Add an epic to the currency pairs watchlist.

    Validates market access first by attempting to fetch 1 price point.
    Returns 403 if the demo account cannot access this market.
    """
    epic = body.get("epic", "").strip()
    if not epic:
        raise HTTPException(400, "epic is required")
    if epic in settings.currency_pairs:
        return {"status": "already_exists", "pairs": settings.currency_pairs}

    # Validate: check we can actually fetch price data for this epic
    if ig_client and ig_client.is_authenticated:
        try:
            resp = await ig_client._request_with_reauth(
                "GET",
                f"{ig_client.base_url}/prices/{epic}/HOUR/1",
                version=2,
            )
            if resp.status_code == 403:
                logger.warning("Cannot add %s — 403 on price data (not available on demo)", epic)
                return {
                    "status": "forbidden",
                    "error": "This market is not available on your demo account. Try the CFD variant instead.",
                    "pairs": settings.currency_pairs,
                }
            if resp.status_code == 404:
                logger.warning("Cannot add %s — 404 market not found", epic)
                return {
                    "status": "not_found",
                    "error": "Market not found. This epic may be invalid.",
                    "pairs": settings.currency_pairs,
                }
        except Exception as e:
            logger.warning("Validation check failed for %s: %s — adding anyway", epic, e)

    settings.currency_pairs.append(epic)
    # Clear forbidden cache so the new epic gets a fresh chance
    if auto_trader:
        auto_trader._forbidden_epics.discard(epic)
    # Persist to DB
    db.add_watchlist_pair(epic)
    logger.info("Added %s to watchlist. Total pairs: %d", epic, len(settings.currency_pairs))
    return {"status": "added", "pairs": settings.currency_pairs}


@app.post("/api/watchlist/remove")
async def remove_from_watchlist(body: dict):
    """Remove an epic from the currency pairs watchlist."""
    epic = body.get("epic", "").strip()
    if not epic:
        raise HTTPException(400, "epic is required")
    if epic not in settings.currency_pairs:
        return {"status": "not_found", "pairs": settings.currency_pairs}
    settings.currency_pairs.remove(epic)
    # Also remove from auto_trader market_data and forbidden cache
    if auto_trader:
        auto_trader.market_data.pop(epic, None)
        auto_trader._forbidden_epics.discard(epic)
    # Persist to DB
    db.remove_watchlist_pair(epic)
    logger.info("Removed %s from watchlist. Total pairs: %d", epic, len(settings.currency_pairs))
    return {"status": "removed", "pairs": settings.currency_pairs}


@app.post("/api/watchlist/reorder")
async def reorder_watchlist(body: dict):
    """Replace the watchlist with a new ordered list."""
    pairs = body.get("pairs", [])
    if not isinstance(pairs, list):
        raise HTTPException(400, "pairs must be a list")
    settings.currency_pairs = pairs
    # Persist to DB
    db.save_watchlist(pairs)
    return {"status": "updated", "pairs": settings.currency_pairs}


# --- WebSocket for real-time updates ---


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        while True:
            # Keep connection alive, listen for client messages
            data = await ws.receive_text()
            # Client can send commands via WS if needed
    except WebSocketDisconnect:
        ws_clients.discard(ws)
    except Exception:
        ws_clients.discard(ws)


async def broadcast_loop():
    """Broadcast trader state to all connected WebSocket clients every 2 seconds."""
    while True:
        await asyncio.sleep(2)
        if not ws_clients or not auto_trader:
            continue
        state = auto_trader.get_state()
        message = json.dumps(state)
        disconnected = set()
        for ws in ws_clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)
        ws_clients -= disconnected


# --- Serve frontend static files ---

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Never intercept API or WebSocket routes
        if full_path.startswith("api/") or full_path.startswith("ws"):
            raise HTTPException(404, "Not found")
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
