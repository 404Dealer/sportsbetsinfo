"""Kalshi prediction market API client.

Documentation: https://trading-api.readme.io/reference/getting-started
Uses RSA key authentication.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from sportsbetsinfo.clients.base import BaseAPIClient
from sportsbetsinfo.core.exceptions import APIError


class KalshiClient(BaseAPIClient):
    """Client for Kalshi prediction market API.

    Kalshi provides markets for event-based predictions including
    sports outcomes. Uses RSA key authentication.
    """

    API_VERSION = "v2"
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

    def __init__(
        self,
        api_key: str,
        private_key_path: Path,
        rate_limit: float = 10.0,
    ) -> None:
        """Initialize Kalshi client with RSA authentication.

        Args:
            api_key: Kalshi API key ID (from API keys page)
            private_key_path: Path to RSA private key file (.pem)
            rate_limit: Requests per second (default 10)
        """
        super().__init__(
            base_url=self.BASE_URL,
            rate_limit=rate_limit,
        )
        self.api_key = api_key
        self._private_key = self._load_private_key(private_key_path)

    def _load_private_key(self, key_path: Path) -> rsa.RSAPrivateKey:
        """Load RSA private key from file.

        Args:
            key_path: Path to PEM-encoded private key

        Returns:
            RSA private key object
        """
        key_data = key_path.read_bytes()
        private_key = serialization.load_pem_private_key(key_data, password=None)
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise APIError("KalshiClient", "Invalid key type: expected RSA private key")
        return private_key

    def _sign_request(self, method: str, path: str, timestamp_ms: int) -> str:
        """Create RSA-PSS signature for request.

        Kalshi signature format: sign(timestamp_ms + method + path)
        Uses RSA-PSS padding with SHA256.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path (e.g., /trade-api/v2/markets)
            timestamp_ms: Unix timestamp in milliseconds

        Returns:
            Base64-encoded signature
        """
        # Kalshi requires full path including /trade-api/v2 prefix
        full_path = f"/trade-api/v2{path}"
        # Strip query parameters before signing
        path_without_query = full_path.split("?")[0]
        message = f"{timestamp_ms}{method}{path_without_query}".encode("utf-8")
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Get authentication headers for a request.

        Args:
            method: HTTP method
            path: Request path

        Returns:
            Dictionary with auth headers
        """
        timestamp_ms = int(time.time() * 1000)
        signature = self._sign_request(method, path, timestamp_ms)

        return {
            "KALSHI-ACCESS-KEY": self.api_key,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms),
        }

    async def authenticate(self) -> None:
        """Verify authentication works by fetching account info.

        RSA auth doesn't require a login step, but we verify
        credentials work by making a test request.
        """
        # Make a simple request to verify auth works
        await self.get_exchange_status()

    async def get_exchange_status(self) -> dict[str, Any]:
        """Get exchange status (also verifies auth).

        Returns:
            Dictionary with exchange status
        """
        path = "/exchange/status"
        response = await self.get(
            path,
            headers=self._auth_headers("GET", path),
        )
        return response.json()

    async def get_markets(self, **kwargs: Any) -> dict[str, Any]:
        """Get available markets.

        Kwargs:
            series_ticker: Filter by series (e.g., "NBA")
            status: Market status ("open", "closed", etc.)
            limit: Maximum results (default 100)
            cursor: Pagination cursor

        Returns:
            Dictionary with markets and pagination info
        """
        path = "/markets"
        params = {
            "status": kwargs.get("status", "open"),
            "limit": kwargs.get("limit", 100),
        }
        if "series_ticker" in kwargs:
            params["series_ticker"] = kwargs["series_ticker"]
        if "cursor" in kwargs:
            params["cursor"] = kwargs["cursor"]

        response = await self.get(
            path,
            headers=self._auth_headers("GET", path),
            params={k: v for k, v in params.items() if v is not None},
        )
        return response.json()

    async def get_odds(self, market_id: str) -> dict[str, Any]:
        """Get current orderbook for a market.

        Args:
            market_id: Kalshi market ticker

        Returns:
            Dictionary with orderbook data (yes/no bids/asks)
        """
        path = f"/markets/{market_id}/orderbook"
        response = await self.get(
            path,
            headers=self._auth_headers("GET", path),
        )
        return response.json()

    async def get_market(self, market_id: str) -> dict[str, Any]:
        """Get detailed market information.

        Args:
            market_id: Kalshi market ticker

        Returns:
            Dictionary with full market details
        """
        path = f"/markets/{market_id}"
        response = await self.get(
            path,
            headers=self._auth_headers("GET", path),
        )
        return response.json()

    async def get_events(self, **kwargs: Any) -> dict[str, Any]:
        """Get events (groups of related markets).

        Kwargs:
            series_ticker: Filter by series
            status: Event status
            limit: Maximum results
            cursor: Pagination cursor

        Returns:
            Dictionary with events and pagination info
        """
        path = "/events"
        params = {
            "status": kwargs.get("status"),
            "limit": kwargs.get("limit", 100),
        }
        if "series_ticker" in kwargs:
            params["series_ticker"] = kwargs["series_ticker"]
        if "cursor" in kwargs:
            params["cursor"] = kwargs["cursor"]

        response = await self.get(
            path,
            headers=self._auth_headers("GET", path),
            params={k: v for k, v in params.items() if v is not None},
        )
        return response.json()

    async def get_series(self, series_ticker: str) -> dict[str, Any]:
        """Get series information.

        Args:
            series_ticker: Series identifier (e.g., "NBA", "NFL")

        Returns:
            Dictionary with series details
        """
        path = f"/series/{series_ticker}"
        response = await self.get(
            path,
            headers=self._auth_headers("GET", path),
        )
        return response.json()

    def get_version(self) -> str:
        """Get API version string."""
        return f"kalshi_{self.API_VERSION}"

    def normalize_market_data(self, market: dict[str, Any]) -> dict[str, Any]:
        """Normalize Kalshi market data to standard format.

        Args:
            market: Raw Kalshi market data

        Returns:
            Normalized dictionary with standard fields
        """
        # Extract yes price (in cents, convert to probability)
        yes_bid = market.get("yes_bid", 0) / 100 if market.get("yes_bid") else None
        yes_ask = market.get("yes_ask", 0) / 100 if market.get("yes_ask") else None
        no_bid = market.get("no_bid", 0) / 100 if market.get("no_bid") else None
        no_ask = market.get("no_ask", 0) / 100 if market.get("no_ask") else None

        # Mid price as implied probability
        if yes_bid is not None and yes_ask is not None:
            implied_prob = (yes_bid + yes_ask) / 2
        elif yes_bid is not None:
            implied_prob = yes_bid
        elif yes_ask is not None:
            implied_prob = yes_ask
        else:
            implied_prob = None

        return {
            "source": "kalshi",
            "market_id": market.get("ticker"),
            "title": market.get("title"),
            "status": market.get("status"),
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
            "implied_probability": implied_prob,
            "volume": market.get("volume"),
            "open_interest": market.get("open_interest"),
            "close_time": market.get("close_time"),
        }
