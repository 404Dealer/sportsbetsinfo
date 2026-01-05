"""Base API client with rate limiting and error handling."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from sportsbetsinfo.core.exceptions import APIError


class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, requests_per_second: float) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second
        """
        self.rate = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request can be made."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class BaseAPIClient(ABC):
    """Abstract base class for API clients.

    Provides:
    - Async HTTP client management
    - Rate limiting
    - Error handling
    - Version tracking
    """

    def __init__(
        self,
        base_url: str,
        rate_limit: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        """Initialize client.

        Args:
            base_url: API base URL
            rate_limit: Requests per second
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.rate_limiter = RateLimiter(rate_limit)
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BaseAPIClient:
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a rate-limited HTTP request.

        Args:
            method: HTTP method
            path: URL path
            **kwargs: Additional httpx request arguments

        Returns:
            HTTP response

        Raises:
            APIError: On request failure
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        await self.rate_limiter.acquire()

        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            raise APIError(
                client=self.__class__.__name__,
                message=str(e),
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise APIError(
                client=self.__class__.__name__,
                message=str(e),
            ) from e

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make GET request."""
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make POST request."""
        return await self._request("POST", path, **kwargs)

    @abstractmethod
    async def get_markets(self, **kwargs: Any) -> dict[str, Any]:
        """Get available markets.

        Returns:
            Dictionary with market data
        """
        pass

    @abstractmethod
    async def get_odds(self, market_id: str) -> dict[str, Any]:
        """Get odds for a specific market.

        Args:
            market_id: Market identifier

        Returns:
            Dictionary with odds data
        """
        pass

    @abstractmethod
    def get_version(self) -> str:
        """Get API version string for source tracking.

        Returns:
            Version string (e.g., "kalshi_v2", "odds_api_v4")
        """
        pass
