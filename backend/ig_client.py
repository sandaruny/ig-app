import httpx
import logging
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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

    async def get_prices(
        self,
        epic: str,
        resolution: str = "HOUR",
        num_points: int = 50,
    ) -> dict:
        """Fetch historical prices for technical analysis."""
        resp = await self._request_with_reauth(
            "GET",
            f"{self.base_url}/prices/{epic}/{resolution}/{num_points}",
            version=2,
        )
        resp.raise_for_status()
        return resp.json()

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
