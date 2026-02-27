"""
Base scraper class for all data source scrapers.

Provides common functionality:
- Rate limiting
- Retry logic with exponential backoff
- Rotating user agents
- Session management
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests
from fake_useragent import UserAgent
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class BaseScraper(ABC):
    """Abstract base class for all data scrapers."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the scraper.

        Args:
            config: Configuration dictionary for this scraper
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # User agent rotation
        try:
            self._ua = UserAgent()
        except Exception:
            # Fallback if fake_useragent fails
            self._ua = None
            self._fallback_ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

        # Session for connection pooling
        self.session = requests.Session()

        # Rate limiting
        self._last_request_time: float = 0
        self._min_request_interval = config.get('rate_limit_seconds', 2.0)

        # Timeout
        self._timeout = config.get('timeout', 30)

        # Retry settings
        self._max_retries = config.get('retry_attempts', 3)

    def _get_user_agent(self) -> str:
        """Get a random user agent string."""
        if self._ua:
            try:
                return self._ua.random
            except Exception:
                pass
        return self._fallback_ua

    def _get_headers(self) -> Dict[str, str]:
        """Generate headers with rotating user agent."""
        return {
            'User-Agent': self._get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            sleep_time = self._min_request_interval - elapsed
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _fetch_url(self, url: str, **kwargs) -> requests.Response:
        """
        Fetch URL with retry logic and rate limiting.

        Args:
            url: URL to fetch
            **kwargs: Additional arguments for requests.get()

        Returns:
            Response object

        Raises:
            requests.RequestException: If all retries fail
        """
        self._rate_limit()

        headers = {**self._get_headers(), **kwargs.pop('headers', {})}

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=4, max=60),
            retry=retry_if_exception_type(
                (requests.RequestException, ConnectionError, TimeoutError)
            ),
            before_sleep=lambda retry_state: self.logger.warning(
                f"Retry attempt {retry_state.attempt_number} for {url}"
            ),
        )
        def _fetch_with_retry() -> requests.Response:
            response = self.session.get(
                url,
                headers=headers,
                timeout=self._timeout,
                **kwargs
            )
            response.raise_for_status()
            return response

        return _fetch_with_retry()

    def _fetch_url_no_retry(self, url: str, **kwargs) -> requests.Response:
        """
        Fetch URL without retry logic (for testing or specific cases).

        Args:
            url: URL to fetch
            **kwargs: Additional arguments for requests.get()

        Returns:
            Response object
        """
        self._rate_limit()
        headers = {**self._get_headers(), **kwargs.pop('headers', {})}
        response = self.session.get(
            url,
            headers=headers,
            timeout=self._timeout,
            **kwargs
        )
        response.raise_for_status()
        return response

    @abstractmethod
    def fetch_data(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Fetch data for given symbols. Must be implemented by subclasses.

        Args:
            symbols: List of ticker symbols to fetch

        Returns:
            Dictionary mapping symbols to their data
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the name of this data source."""
        pass

    def close(self) -> None:
        """Close the session and clean up resources."""
        self.session.close()

    def __enter__(self) -> "BaseScraper":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
