"""
Local price cache to minimise IG historical price data API consumption.

IG demo accounts have a hard limit of 10,000 price data points per week.
Without caching, each analysis cycle fetches 35 candles × N pairs = hundreds
of points.  With caching:

  - First fetch: full 35 candles (35 points)
  - Subsequent fetches: only 2-3 new candles since last fetch (~3 points)
  - Merge into the cached history and trim to 35

This reduces weekly consumption by ~95%.
"""

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Maximum number of candles to keep per epic
MAX_CANDLES = 50
# Default number of new candles to fetch on a refresh (small delta)
DELTA_CANDLES = 4
# Minimum seconds between refreshes for the same epic/resolution
MIN_REFRESH_INTERVAL = 120  # 2 minutes


class PriceCache:
    """In-memory cache of historical price candles per epic."""

    def __init__(self):
        # {epic: {"resolution": str, "prices": [...], "last_fetch": float,
        #         "last_snapshot_time": str}}
        self._cache: dict[str, dict] = {}
        self._stats = {
            "hits": 0,         # served from cache without API call
            "delta_fetches": 0, # small delta refreshes
            "full_fetches": 0,  # full initial fetches
            "points_saved": 0,  # data points NOT consumed thanks to caching
        }

    def get_cached(self, epic: str, resolution: str) -> dict | None:
        """Return cached price data if available and fresh enough.

        Returns None if cache is empty or stale.
        Returns the cached dict (in IG response format) if still fresh.
        """
        entry = self._cache.get(epic)
        if not entry:
            return None
        if entry.get("resolution") != resolution:
            return None
        # Check if we have enough candles
        if len(entry.get("prices", [])) < 20:
            return None
        return entry

    def needs_refresh(self, epic: str, resolution: str) -> bool:
        """Check if the cache for this epic needs a refresh."""
        entry = self._cache.get(epic)
        if not entry or entry.get("resolution") != resolution:
            return True
        if len(entry.get("prices", [])) < 20:
            return True
        elapsed = time.time() - entry.get("last_fetch", 0)
        return elapsed >= MIN_REFRESH_INTERVAL

    def get_fetch_params(self, epic: str, resolution: str, full_count: int = 35) -> dict:
        """Determine what to fetch from IG.

        Returns a dict with:
          - "mode": "full" or "delta"
          - "num_points": how many candles to request
        """
        entry = self._cache.get(epic)
        if not entry or entry.get("resolution") != resolution:
            return {"mode": "full", "num_points": full_count}
        if len(entry.get("prices", [])) < 20:
            return {"mode": "full", "num_points": full_count}
        # We have a good cache — only fetch the delta
        return {"mode": "delta", "num_points": DELTA_CANDLES}

    def update(self, epic: str, resolution: str, response: dict, mode: str):
        """Merge new price data into the cache.

        Args:
            epic: Market epic
            resolution: Price resolution (e.g. "HOUR")
            response: Raw IG price API response
            mode: "full" or "delta"
        """
        new_prices = response.get("prices", [])
        if not new_prices:
            return

        entry = self._cache.get(epic)

        if mode == "full" or not entry or entry.get("resolution") != resolution:
            # Full replace
            self._cache[epic] = {
                "resolution": resolution,
                "prices": new_prices[-MAX_CANDLES:],
                "last_fetch": time.time(),
                "last_snapshot_time": new_prices[-1].get("snapshotTime", ""),
            }
            self._stats["full_fetches"] += 1
            logger.debug(
                "Cache FULL for %s: %d candles stored", epic, len(new_prices)
            )
            return

        # Delta merge: append new candles, deduplicate by snapshotTime
        existing = entry.get("prices", [])
        existing_times = {p.get("snapshotTime") for p in existing}

        added = 0
        for p in new_prices:
            snap = p.get("snapshotTime")
            if snap and snap not in existing_times:
                existing.append(p)
                existing_times.add(snap)
                added += 1

        # Also update the last candle (it may have changed — live candle)
        if new_prices and existing:
            latest_new = new_prices[-1]
            latest_snap = latest_new.get("snapshotTime")
            # Find and replace the matching candle
            for i in range(len(existing) - 1, -1, -1):
                if existing[i].get("snapshotTime") == latest_snap:
                    existing[i] = latest_new
                    break

        # Trim to max size (keep most recent)
        if len(existing) > MAX_CANDLES:
            existing = existing[-MAX_CANDLES:]

        entry["prices"] = existing
        entry["last_fetch"] = time.time()
        if new_prices:
            entry["last_snapshot_time"] = new_prices[-1].get("snapshotTime", "")

        self._stats["delta_fetches"] += 1
        self._stats["points_saved"] += (35 - len(new_prices))

        logger.debug(
            "Cache DELTA for %s: +%d new candles (total %d, saved ~%d API points)",
            epic, added, len(existing), 35 - len(new_prices),
        )

    def get_prices_response(self, epic: str) -> dict:
        """Return cached data formatted as an IG prices API response."""
        entry = self._cache.get(epic)
        if not entry:
            return {"prices": []}
        return {"prices": entry.get("prices", [])}

    def invalidate(self, epic: str):
        """Remove cached data for an epic."""
        self._cache.pop(epic, None)

    def clear(self):
        """Clear all cached data."""
        self._cache.clear()

    def get_stats(self) -> dict:
        """Return cache statistics."""
        total_cached = sum(len(e.get("prices", [])) for e in self._cache.values())
        return {
            **self._stats,
            "cachedEpics": len(self._cache),
            "totalCachedCandles": total_cached,
        }


# Singleton instance
price_cache = PriceCache()
