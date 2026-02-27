"""
Investing.com futures data scraper.

Note: Investing.com has aggressive Cloudflare protection.
This scraper attempts to fetch data using Playwright with JavaScript rendering.
If it fails, the main agent will fall back to Yahoo Finance futures data.

For reliability, consider this a secondary confirmation source.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base_scraper import BaseScraper


@dataclass
class InvestingFuturesData:
    """Data container for futures contract information from Investing.com."""

    symbol: str
    name: str
    last_price: float
    change: float
    change_percent: float
    high: float
    low: float
    time: str
    open_price: Optional[float] = None
    prev_close: Optional[float] = None


class InvestingComScraper(BaseScraper):
    """
    Scraper for Investing.com futures data.

    IMPORTANT: Investing.com uses heavy JavaScript rendering and Cloudflare protection.
    This scraper uses Playwright with Chromium for JS execution.

    The first run will download Chromium (~150MB). Run 'playwright install chromium'
    after installing dependencies.

    If this scraper fails consistently, the main agent will use Yahoo Finance
    futures data as a fallback (ES=F, NQ=F, YM=F).
    """

    BASE_URL = "https://www.investing.com"

    # Contract URL mappings
    FUTURES_URLS = {
        'ES': '/indices/us-spx-500-futures',
        'NQ': '/indices/nq-100-futures',
        'YM': '/indices/us-30-futures',
        'RTY': '/indices/smallcap-2000-futures',
        'CL': '/commodities/crude-oil',
        'GC': '/commodities/gold',
    }

    FUTURES_NAMES = {
        'ES': 'E-mini S&P 500',
        'NQ': 'E-mini NASDAQ 100',
        'YM': 'E-mini Dow Jones',
        'RTY': 'E-mini Russell 2000',
        'CL': 'Crude Oil WTI',
        'GC': 'Gold',
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._min_request_interval = config.get('rate_limit_seconds', 8.0)
        self._use_js_render = config.get('javascript_render', True)
        self._playwright = None
        self._browser = None
        self._browser_ready = False

    def _ensure_browser(self):
        """Lazy initialization of Playwright browser."""
        if self._browser is None:
            try:
                from playwright.sync_api import sync_playwright

                if not self._browser_ready:
                    self.logger.info(
                        "Initializing Playwright browser for JS rendering..."
                    )

                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                    ]
                )
                self._browser_ready = True

            except ImportError:
                self.logger.error(
                    "playwright not installed. "
                    "Install with: pip install playwright && playwright install chromium"
                )
                raise
            except Exception as e:
                self.logger.error(f"Failed to initialize browser: {e}")
                raise

        return self._browser

    def get_source_name(self) -> str:
        return "Investing.com"

    def fetch_data(self, symbols: List[str]) -> Dict[str, InvestingFuturesData]:
        """
        Fetch futures data for specified contracts.

        Args:
            symbols: List of contract codes (ES, NQ, YM, etc.)

        Returns:
            Dictionary mapping contract codes to InvestingFuturesData objects
        """
        results = {}

        for symbol in symbols:
            if symbol not in self.FUTURES_URLS:
                self.logger.warning(f"Unknown futures symbol: {symbol}")
                continue

            try:
                data = self._fetch_futures_contract(symbol)
                if data:
                    results[symbol] = data
            except Exception as e:
                self.logger.error(f"Investing.com failed for {symbol}: {e}")
                continue

        return results

    def _fetch_futures_contract(self, symbol: str) -> Optional[InvestingFuturesData]:
        """Fetch data for a single futures contract."""
        url = f"{self.BASE_URL}{self.FUTURES_URLS[symbol]}"

        self._rate_limit()

        if self._use_js_render:
            return self._fetch_with_playwright(url, symbol)
        else:
            return self._fetch_static(url, symbol)

    def _fetch_with_playwright(
        self, url: str, symbol: str
    ) -> Optional[InvestingFuturesData]:
        """Fetch page with JavaScript rendering using Playwright."""
        page = None
        try:
            browser = self._ensure_browser()

            # Create a new context with realistic settings
            context = browser.new_context(
                user_agent=self._get_user_agent(),
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
            )

            page = context.new_page()

            # Navigate and wait for content
            page.goto(url, wait_until='networkidle', timeout=30000)

            # Wait for price element to appear
            page.wait_for_selector(
                '[data-test="instrument-price-last"], .instrument-price_last__KQzyA, #last_last',
                timeout=10000
            )

            # Get the page content
            content = page.content()

            # Parse the rendered HTML
            result = self._parse_futures_page(content, symbol)

            context.close()
            return result

        except Exception as e:
            self.logger.warning(f"Playwright fetch failed for {symbol}: {e}")
            if page:
                try:
                    page.context.close()
                except Exception:
                    pass
            return None

    def _get_user_agent(self) -> str:
        """Get a realistic user agent string."""
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def _fetch_static(self, url: str, symbol: str) -> Optional[InvestingFuturesData]:
        """Attempt to fetch without JS rendering (likely to fail)."""
        try:
            response = self._fetch_url(url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'lxml')

            # Try to extract data from static HTML
            # This is likely to fail due to JS rendering requirements
            return self._parse_static_page(soup, symbol)

        except Exception as e:
            self.logger.warning(f"Static fetch failed for {symbol}: {e}")
            return None

    def _parse_futures_page(self, html: str, symbol: str) -> Optional[InvestingFuturesData]:
        """Parse the rendered futures page."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            last_price = None
            change = 0.0
            change_percent = 0.0
            high = 0.0
            low = 0.0

            # Try different selectors for price
            price_selectors = [
                '[data-test="instrument-price-last"]',
                '.instrument-price_last__KQzyA',
                '.text-5xl',
                '#last_last',
            ]

            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem:
                    try:
                        last_price = float(elem.get_text().replace(',', '').strip())
                        break
                    except (ValueError, AttributeError):
                        continue

            if last_price is None:
                self.logger.warning(f"Could not find price for {symbol}")
                return None

            # Try to get change
            change_selectors = [
                '[data-test="instrument-price-change"]',
                '.instrument-price_change__cZwKA',
            ]

            for selector in change_selectors:
                elem = soup.select_one(selector)
                if elem:
                    try:
                        text = elem.get_text().replace(',', '').replace('+', '').strip()
                        change = float(text)
                        break
                    except (ValueError, AttributeError):
                        continue

            # Try to get change percent
            pct_selectors = [
                '[data-test="instrument-price-change-percent"]',
                '.instrument-price_change-percent__NCmAr',
            ]

            for selector in pct_selectors:
                elem = soup.select_one(selector)
                if elem:
                    try:
                        text = elem.get_text().strip('()%').replace(',', '').replace('+', '')
                        change_percent = float(text)
                        break
                    except (ValueError, AttributeError):
                        continue

            return InvestingFuturesData(
                symbol=symbol,
                name=self.FUTURES_NAMES.get(symbol, symbol),
                last_price=last_price,
                change=change,
                change_percent=change_percent,
                high=high or last_price,
                low=low or last_price,
                time="",
            )

        except Exception as e:
            self.logger.error(f"Parse error for {symbol}: {e}")
            return None

    def _parse_static_page(self, soup, symbol: str) -> Optional[InvestingFuturesData]:
        """Parse static HTML (fallback, unlikely to work)."""
        # This is a best-effort attempt for static parsing
        # Most likely won't work due to JS rendering requirements
        self.logger.warning(
            f"Static parsing attempted for {symbol} - may not have accurate data"
        )
        return None

    def close(self) -> None:
        """Close the Playwright browser."""
        super().close()
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
