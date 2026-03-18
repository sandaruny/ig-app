import httpx
import logging
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PriceAllowanceExhausted(Exception):
    """Raised when the weekly IG historical price data allowance is used up."""

    def __init__(self, remaining: int, total: int, expiry_secs: int | None):
        self.remaining = remaining
        self.total = total
        self.expiry_secs = expiry_secs
        mins = (expiry_secs // 60) if expiry_secs else "?"
        hours = (expiry_secs // 3600) if expiry_secs else "?"
        super().__init__(
            f"IG price data allowance exhausted ({remaining}/{total}). "
            f"Resets in ~{hours}h ({mins}min). "
            f"Reduce analysis frequency or wait for reset."
        )


class IGClient:
    """Client for IG Trading REST API with automatic session management."""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.cst: str | None = None
        self.security_token: str | None = None
        self.lightstreamer_endpoint: str | None = None
        self.account_id: str | None = None
        self._client = httpx.AsyncClient(timeout=30.0)

        # Saved credentials for auto-reauth on session expiry
        self._username: str | None = None
        self._password: str | None = None
        self._reauth_lock = asyncio.Lock()

        # Price data allowance tracking (IG limits to 10,000 points/week)
        self.price_allowance: dict = {
            "remaining": None,    # None = unknown until first price response
            "total": 10000,
            "expiry_secs": None,  # seconds until allowance resets
        }

    def _headers(self, version: int = 1) -> dict:
        headers = {
            "X-IG-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json; charset=UTF-8",
            "Version": str(version),
        }
        if self.cst:
            headers["CST"] = self.cst
        if self.security_token:
            headers["X-SECURITY-TOKEN"] = self.security_token
        return headers

    async def login(self, username: str, password: str) -> dict:
        """Authenticate and obtain session tokens."""
        resp = await self._client.post(
            f"{self.base_url}/session",
            headers=self._headers(version=2),
            json={"identifier": username, "password": password},
        )
        resp.raise_for_status()
        self.cst = resp.headers.get("CST")
        self.security_token = resp.headers.get("X-SECURITY-TOKEN")
        data = resp.json()
        self.lightstreamer_endpoint = data.get("lightstreamerEndpoint")
        self.account_id = data.get("currentAccountId")

        # Store credentials for auto-reauth
        self._username = username
        self._password = password

        logger.info(
            "Logged in to IG. Account: %s, LS endpoint: %s",
            self.account_id,
            self.lightstreamer_endpoint,
        )
        return data

    @property
    def is_authenticated(self) -> bool:
        return self.cst is not None and self.security_token is not None

    @property
    def can_reauth(self) -> bool:
        """Whether we have saved credentials to attempt automatic re-login."""
        return self._username is not None and self._password is not None

    async def _reauth(self) -> bool:
        """Attempt to re-authenticate using saved credentials.

        Uses a lock to prevent multiple concurrent re-auth attempts.
        Returns True if re-auth succeeded, False otherwise.
        """
        if not self.can_reauth:
            logger.warning("Cannot re-authenticate: no saved credentials")
            return False

        async with self._reauth_lock:
            # Double-check: another coroutine may have already refreshed
            if self.is_authenticated:
                # Try a lightweight call to verify the session is still valid
                try:
                    resp = await self._client.get(
                        f"{self.base_url}/session",
                        headers=self._headers(version=1),
                    )
                    if resp.status_code != 401:
                        return True
                except Exception:
                    pass

            logger.info("Session expired — attempting automatic re-login...")
            try:
                await self.login(self._username, self._password)
                logger.info("Automatic re-login successful")
                return True
            except Exception as e:
                logger.error("Automatic re-login failed: %s", e)
                self.cst = None
                self.security_token = None
                return False

    async def _request_with_reauth(
        self,
        method: str,
        url: str,
        *,
        version: int = 1,
        json: dict | None = None,
        params: dict | None = None,
        extra_headers: dict | None = None,
    ) -> httpx.Response:
        """Make an HTTP request with automatic re-authentication on 401.

        If the request returns 401 (Unauthorized / session expired), this
        method will attempt to re-login using saved credentials and retry
        the original request once.  For 403 (Forbidden), the error is
        propagated immediately — 403 means the account doesn't have access,
        not that the session is expired.
        """
        headers = self._headers(version=version)
        if extra_headers:
            headers.update(extra_headers)

        kwargs = {"headers": headers}
        if json is not None:
            kwargs["json"] = json
        if params is not None:
            kwargs["params"] = params

        resp = await self._client.request(method, url, **kwargs)
        logger.debug("Request %s %s → %d", method, url, resp.status_code)

        # 401 = session expired → try re-auth once
        if resp.status_code == 401 and self.can_reauth:
            logger.warning("Got 401 for %s %s — attempting re-auth", method, url)
            if await self._reauth():
                # Rebuild headers with fresh tokens
                headers = self._headers(version=version)
                if extra_headers:
                    headers.update(extra_headers)
                kwargs["headers"] = headers
                resp = await self._client.request(method, url, **kwargs)

        return resp

    # ── Public API methods ────────────────────────────────────────

    async def search_markets(self, search_term: str) -> list[dict]:
        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/markets",
            version=1,
            params={"searchTerm": search_term},
        )
        resp.raise_for_status()
        return resp.json().get("markets", [])

    async def get_market_details(self, epic: str) -> dict:
        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/markets/{epic}",
            version=3,
        )
        resp.raise_for_status()
        return resp.json()

    # IG error codes that indicate the weekly price data limit is hit
    _ALLOWANCE_ERROR_CODES = {
        "error.public-api.exceeded-account-historical-data-allowance",
        "error.public-api.exceeded-api-key-allowance",
    }

    async def get_prices(
        self,
        epic: str,
        resolution: str = "HOUR",
        num_points: int = 50,
    ) -> dict:
        """Fetch historical prices for technical analysis.

        Tracks the weekly price data allowance from the response and raises
        PriceAllowanceExhausted when the limit is hit.
        """
        # If we already know the allowance is exhausted, fail fast
        if (self.price_allowance["remaining"] is not None
                and self.price_allowance["remaining"] <= 0):
            raise PriceAllowanceExhausted(
                remaining=0,
                total=self.price_allowance["total"],
                expiry_secs=self.price_allowance["expiry_secs"],
            )

        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/prices/{epic}/{resolution}/{num_points}",
            version=2,
        )

        # On 403, inspect the response body to distinguish allowance
        # exhaustion from genuine market-level access denial
        if resp.status_code == 403:
            error_code = ""
            try:
                error_body = resp.json()
                error_code = error_body.get("errorCode", "")
            except Exception:
                pass

            if error_code in self._ALLOWANCE_ERROR_CODES:
                # Mark allowance as exhausted
                self.price_allowance["remaining"] = 0
                logger.error(
                    "IG price data allowance EXHAUSTED (errorCode=%s). "
                    "All price requests will fail until weekly reset.",
                    error_code,
                )
                raise PriceAllowanceExhausted(
                    remaining=0,
                    total=self.price_allowance["total"],
                    expiry_secs=self.price_allowance["expiry_secs"],
                )

            # Not an allowance issue — genuine market 403
            logger.warning("403 for %s: %s", epic, error_code or "unknown")
            resp.raise_for_status()

        resp.raise_for_status()
        data = resp.json()

        # Update allowance tracking from the response
        allowance = data.get("allowance")
        if allowance:
            self.price_allowance["remaining"] = allowance.get("remainingAllowance")
            self.price_allowance["total"] = allowance.get("totalAllowance", 10000)
            self.price_allowance["expiry_secs"] = allowance.get("allowanceExpiry")
            remaining = self.price_allowance["remaining"]
            total = self.price_allowance["total"]
            if remaining is not None:
                if remaining <= 0:
                    logger.error(
                        "IG price data allowance EXHAUSTED (0/%d). "
                        "Resets in %s seconds.",
                        total, self.price_allowance["expiry_secs"],
                    )
                elif remaining < total * 0.1:
                    logger.warning(
                        "IG price data allowance LOW: %d/%d remaining (%.0f%%). "
                        "Resets in %s seconds.",
                        remaining, total,
                        (remaining / total) * 100,
                        self.price_allowance["expiry_secs"],
                    )

        return data

    async def get_open_positions(self) -> list[dict]:
        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/positions",
            version=2,
        )
        resp.raise_for_status()
        return resp.json().get("positions", [])

    async def open_position(
        self,
        epic: str,
        direction: str,
        size: float,
        stop_distance: float | None = None,
        limit_distance: float | None = None,
        currency_code: str = "USD",
        force_open: bool = True,
        guaranteed_stop: bool = False,
    ) -> dict:
        """Open a new OTC position.

        stop_distance and limit_distance are in IG points (not raw price).
        """
        payload = {
            "epic": epic,
            "direction": direction,  # BUY or SELL
            "size": str(size),
            "orderType": "MARKET",
            "currencyCode": currency_code,
            "forceOpen": force_open,
            "guaranteedStop": guaranteed_stop,
            "expiry": "-",
        }
        if stop_distance is not None:
            payload["stopDistance"] = round(float(stop_distance), 1)
        if limit_distance is not None:
            payload["limitDistance"] = round(float(limit_distance), 1)

        logger.info(
            "Opening position: %s %s size=%s stop=%s limit=%s",
            direction, epic, size,
            payload.get("stopDistance"), payload.get("limitDistance"),
        )

        resp = await self._request_with_reauth(
            "POST",
            f"{self.base_url}/positions/otc",
            version=2,
            json=payload,
        )
        resp.raise_for_status()
        deal_ref = resp.json()
        # Confirm the deal
        confirmation = await self.get_deal_confirmation(deal_ref["dealReference"])
        return confirmation

    async def close_position(
        self,
        deal_id: str,
        direction: str,
        size: float,
        order_type: str = "MARKET",
    ) -> dict:
        """Close an existing position."""
        payload = {
            "dealId": deal_id,
            "direction": direction,  # Opposite of open direction
            "size": str(size),
            "orderType": order_type,
        }
        resp = await self._request_with_reauth(
            "DELETE",
            f"{self.base_url}/positions/otc",
            version=1,
            json=payload,
            extra_headers={"_method": "DELETE"},
        )
        resp.raise_for_status()
        deal_ref = resp.json()
        return await self.get_deal_confirmation(deal_ref["dealReference"])

    async def get_deal_confirmation(self, deal_reference: str) -> dict:
        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/confirms/{deal_reference}",
            version=1,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_accounts(self) -> list[dict]:
        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/accounts",
            version=1,
        )
        resp.raise_for_status()
        return resp.json().get("accounts", [])

    async def get_client_sentiment(self, market_id: str) -> dict:
        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/clientsentiment/{market_id}",
            version=1,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_activity_history(self) -> list[dict]:
        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/history/activity",
            version=3,
        )
        resp.raise_for_status()
        return resp.json().get("activities", [])

    async def close(self):
        await self._client.aclose()
