"""
Retry queue for failed database sync operations.

When a trade-related DB write fails (save, update P&L, close status),
the operation is queued here and retried with exponential backoff.

Backoff schedule: 5s → 10s → 20s → 40s → 80s → 160s → 300s (cap)
Max retries: 15 (then the item is moved to a dead-letter list)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import database as db

logger = logging.getLogger(__name__)


class SyncOp(str, Enum):
    SAVE_TRADE = "save_trade"
    UPDATE_PNL = "update_pnl"
    UPDATE_STATUS = "update_status"


@dataclass
class RetryItem:
    op: SyncOp
    payload: dict
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    next_retry_at: float = 0.0
    last_error: str = ""

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        return {
            "op": self.op.value,
            "deal_id": self._deal_id,
            "attempts": self.attempts,
            "nextRetryIn": max(0, round(self.next_retry_at - time.time(), 1)),
            "lastError": self.last_error,
            "age": round(self.age_seconds, 1),
        }

    @property
    def _deal_id(self) -> str:
        return self.payload.get("deal_id", "?")


# ── Backoff config ────────────────────────────────────────────────
INITIAL_BACKOFF = 5.0       # seconds
BACKOFF_MULTIPLIER = 2.0
MAX_BACKOFF = 300.0         # 5 minutes cap
MAX_RETRIES = 15


def _next_backoff(attempts: int) -> float:
    delay = INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempts)
    return min(delay, MAX_BACKOFF)


# ── The retry queue ──────────────────────────────────────────────

class SyncRetryQueue:
    """Thread-safe queue for retrying failed DB sync operations."""

    def __init__(self):
        self._queue: list[RetryItem] = []
        self._dead: list[RetryItem] = []    # permanently failed items
        self._task: asyncio.Task | None = None
        self._total_retried: int = 0
        self._total_succeeded: int = 0
        self._total_dead: int = 0

    # ── Public API ────────────────────────────────────────────────

    def enqueue(self, op: SyncOp, payload: dict, error: str = ""):
        """Add a failed operation to the retry queue."""
        item = RetryItem(
            op=op,
            payload=payload,
            next_retry_at=time.time() + INITIAL_BACKOFF,
            last_error=error,
        )
        self._queue.append(item)
        logger.warning(
            "Sync retry queued: %s for deal %s (error: %s). Queue depth: %d",
            op.value, item._deal_id, error, len(self._queue),
        )

    def start(self):
        """Start the background retry loop."""
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._retry_loop())
        logger.info("SyncRetryQueue background loop started")

    def stop(self):
        """Stop the background retry loop."""
        if self._task:
            self._task.cancel()
            self._task = None

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    @property
    def dead_count(self) -> int:
        return len(self._dead)

    def get_status(self) -> dict:
        """Return the current sync retry status for the API/dashboard."""
        return {
            "pending": len(self._queue),
            "dead": len(self._dead),
            "totalRetried": self._total_retried,
            "totalSucceeded": self._total_succeeded,
            "totalDead": self._total_dead,
            "queue": [item.to_dict() for item in self._queue[:20]],  # first 20
            "deadLetters": [item.to_dict() for item in self._dead[:10]],
        }

    def retry_dead(self):
        """Move all dead-letter items back to the active queue for another round."""
        if not self._dead:
            return 0
        count = len(self._dead)
        now = time.time()
        for item in self._dead:
            item.attempts = 0
            item.next_retry_at = now + INITIAL_BACKOFF
            self._queue.append(item)
        self._dead.clear()
        logger.info("Moved %d dead-letter items back to retry queue", count)
        return count

    def flush_now(self):
        """Reset backoff timers on all pending items so they retry immediately."""
        now = time.time()
        flushed = 0
        for item in self._queue:
            if item.next_retry_at > now:
                item.next_retry_at = now
                flushed += 1
        # Also move dead letters back
        if self._dead:
            for item in self._dead:
                item.attempts = 0
                item.next_retry_at = now
                self._queue.append(item)
            flushed += len(self._dead)
            self._dead.clear()
        if flushed:
            logger.info("Flushed sync queue: %d items set to retry immediately", flushed)
        return flushed

    # ── Background loop ───────────────────────────────────────────

    async def _retry_loop(self):
        """Process the queue every second, executing items whose backoff has elapsed."""
        while True:
            try:
                await asyncio.sleep(1)
                await self._process_due_items()
            except asyncio.CancelledError:
                logger.info("SyncRetryQueue loop cancelled")
                break
            except Exception as e:
                logger.error("SyncRetryQueue loop error: %s", e)
                await asyncio.sleep(5)

    async def _process_due_items(self):
        now = time.time()
        still_pending: list[RetryItem] = []

        for item in self._queue:
            if item.next_retry_at > now:
                still_pending.append(item)
                continue

            # Attempt the retry
            item.attempts += 1
            self._total_retried += 1
            success = self._execute(item)

            if success:
                self._total_succeeded += 1
                logger.info(
                    "Sync retry succeeded: %s for deal %s after %d attempts",
                    item.op.value, item._deal_id, item.attempts,
                )
            elif item.attempts >= MAX_RETRIES:
                # Move to dead-letter queue
                self._dead.append(item)
                self._total_dead += 1
                logger.error(
                    "Sync retry exhausted: %s for deal %s after %d attempts — moved to dead letter. Error: %s",
                    item.op.value, item._deal_id, item.attempts, item.last_error,
                )
            else:
                # Schedule next retry with backoff
                item.next_retry_at = now + _next_backoff(item.attempts)
                still_pending.append(item)
                logger.info(
                    "Sync retry failed (attempt %d/%d): %s for deal %s — next in %.0fs. Error: %s",
                    item.attempts, MAX_RETRIES, item.op.value,
                    item._deal_id, item.next_retry_at - now, item.last_error,
                )

        self._queue = still_pending

    # ── Execute a single sync operation ───────────────────────────

    def _execute(self, item: RetryItem) -> bool:
        """Try to execute the DB operation. Returns True on success."""
        try:
            if item.op == SyncOp.SAVE_TRADE:
                db.save_trade(item.payload)

            elif item.op == SyncOp.UPDATE_PNL:
                db.update_trade_pnl(
                    deal_id=item.payload["deal_id"],
                    pnl=item.payload["pnl"],
                )

            elif item.op == SyncOp.UPDATE_STATUS:
                db.update_trade_status(
                    deal_id=item.payload["deal_id"],
                    status=item.payload["status"],
                    pnl=item.payload.get("pnl"),
                    close_level=item.payload.get("close_level"),
                    closed_at=item.payload.get("closed_at"),
                )
            else:
                logger.error("Unknown sync op: %s", item.op)
                return False

            return True

        except Exception as e:
            item.last_error = str(e)
            return False


# ── Module-level singleton ────────────────────────────────────────
sync_queue = SyncRetryQueue()
