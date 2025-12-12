# hummingbot_api_wrapper.py
"""Utility wrapper around HummingbotAPIClient that adds health checks and fallback.

- Checks the Hummingbot API health endpoint (`/status` or `/health`).
- Retries a configurable number of times with exponential back‑off.
- If the API is unhealthy or unreachable, falls back to `MockDataClient`.
- Provides a single method `get_v4_quote_safe` that mirrors `HummingbotAPIClient.get_v4_quote`.
"""

import time
import logging
from typing import Any, Dict

from schemas.contracts import QuoteResult
from lib.hummingbot_data_client import HummingbotAPIClient
from lib.mock_data_client import MockDataClient

logger = logging.getLogger(__name__)


class HummingbotAPIWrapper:
    def __init__(self, health_url: str = "http://localhost:8000/status", max_retries: int = 3, backoff_factor: float = 0.5):
        self.client = HummingbotAPIClient()
        self.mock = MockDataClient()
        self.health_url = health_url
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def _is_healthy(self) -> bool:
        """Ping the health endpoint. Returns True if a 2xx response is received."""
        try:
            # Using the client’s internal request method via a quick GET
            import requests
            resp = requests.get(self.health_url, timeout=2)
            healthy = resp.status_code == 200
            logger.debug("Hummingbot health check %s (status %s)", "passed" if healthy else "failed", resp.status_code)
            return healthy
        except Exception as e:
            logger.debug("Hummingbot health check exception: %s", e)
            return False

    def _ensure_healthy(self) -> bool:
        """Retry health check with exponential back‑off. Returns final health status."""
        for attempt in range(1, self.max_retries + 1):
            if self._is_healthy():
                return True
            sleep_time = self.backoff_factor * (2 ** (attempt - 1))
            logger.debug("Health check retry %d/%d after %.2fs", attempt, self.max_retries, sleep_time)
            time.sleep(sleep_time)
        return False

    def get_v4_quote_safe(self, token_in: str, token_out: str, amount_in_wei: int, simulate: bool = False) -> QuoteResult:
        """Return a QuoteResult using the live API if healthy, otherwise fallback to mock."""
        start_ts = time.time()
        
        if self._ensure_healthy():
            try:
                raw_quote = self.client.get_v4_quote(token_in, token_out, amount_in_wei, simulate=simulate)
                # Map raw result to Pydantic model
                return QuoteResult(
                    success=raw_quote.success,
                    simulation_success=raw_quote.simulation_success,
                    amount_out=raw_quote.amount_out,
                    gas_estimate=raw_quote.gas_estimate,
                    latency_ms=(time.time() - start_ts) * 1000,
                    error=raw_quote.error,
                    source="live"
                )
            except Exception as e:
                logger.warning("Live Hummingbot API call failed: %s – falling back to mock", e)
        else:
            logger.warning("Hummingbot API unhealthy – using mock data client")
        
        # Fallback to mock
        try:
            mock_quote = self.mock.get_v4_quote(token_in, token_out, amount_in_wei, simulate=simulate)
            return QuoteResult(
                success=mock_quote.success,
                simulation_success=mock_quote.simulation_success,
                amount_out=mock_quote.amount_out,
                gas_estimate=mock_quote.gas_estimate,
                latency_ms=(time.time() - start_ts) * 1000,
                error=mock_quote.error,
                source="mock"
            )
        except Exception as e:
             # Just in case mock also explodes
             return QuoteResult(success=False, error=str(e), latency_ms=(time.time() - start_ts) * 1000, source="mock_failed")

# Convenience singleton for the rest of the codebase
hummingbot_api = HummingbotAPIWrapper()
