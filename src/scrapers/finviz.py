"""
FINVIZ data scraper for fundamental and technical data.

Scrapes the FINVIZ stock screener for:
- Fundamental metrics (P/E, EPS, etc.)
- Technical indicators
- Analyst recommendations
- Insider activity
- Sector information
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


@dataclass
class FinvizData:
    """Data container for FINVIZ stock information."""

    symbol: str
    sector: str
    industry: str
    country: str
    market_cap: str
    pe_ratio: Optional[float]
    forward_pe: Optional[float]
    peg_ratio: Optional[float]
    price_to_sales: Optional[float]
    price_to_book: Optional[float]
    eps_ttm: Optional[float]
    eps_next_year: Optional[float]
    eps_growth: Optional[float]
    short_float: Optional[float]
    target_price: Optional[float]
    recommendation: Optional[float]  # 1 (Strong Buy) to 5 (Strong Sell)
    insider_own: Optional[float]
    insider_trans: Optional[str]
    inst_own: Optional[float]
    rsi_14: Optional[float]
    sma20_dist: Optional[float]  # Distance from SMA20 (%)
    sma50_dist: Optional[float]
    sma200_dist: Optional[float]
    rel_volume: Optional[float]
    avg_volume: Optional[str]
    price: Optional[float]
    change: Optional[float]


class FinvizScraper(BaseScraper):
    """
    Scraper for FINVIZ stock data.

    FINVIZ serves static HTML, so no JavaScript rendering is needed.
    Uses requests + BeautifulSoup.
    """

    BASE_URL = "https://finviz.com/quote.ashx"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._min_request_interval = config.get('rate_limit_seconds', 3.0)

    def get_source_name(self) -> str:
        return "FINVIZ"

    def fetch_data(self, symbols: List[str]) -> Dict[str, FinvizData]:
        """
        Fetch FINVIZ data for multiple symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary mapping symbols to FinvizData objects
        """
        results = {}

        for symbol in symbols:
            try:
                data = self._fetch_single_stock(symbol)
                if data:
                    results[symbol] = data
            except Exception as e:
                self.logger.error(f"FINVIZ failed for {symbol}: {e}")
                continue

        return results

    def _fetch_single_stock(self, symbol: str) -> Optional[FinvizData]:
        """Fetch FINVIZ data for a single symbol."""
        url = f"{self.BASE_URL}?t={symbol}"

        try:
            response = self._fetch_url(url)
        except Exception as e:
            self.logger.warning(f"Failed to fetch FINVIZ page for {symbol}: {e}")
            return None

        # Check for valid response
        if "not found" in response.text.lower() or response.status_code != 200:
            self.logger.warning(f"Symbol {symbol} not found on FINVIZ")
            return None

        soup = BeautifulSoup(response.text, 'lxml')

        # Find the snapshot table - try multiple possible class names
        snapshot_table = None
        table_selectors = [
            {'class_': 'snapshot-table2'},
            {'class_': 'snapshot-table'},
            {'class_': 'table-dark-row'},
            {'id': 'snapshot-table2'},
        ]

        for selector in table_selectors:
            snapshot_table = soup.find('table', **selector)
            if snapshot_table:
                break

        # Fallback: find any table with typical FINVIZ metrics
        if not snapshot_table:
            for table in soup.find_all('table'):
                text = table.get_text()
                if 'P/E' in text and 'Market Cap' in text:
                    snapshot_table = table
                    break

        if not snapshot_table:
            self.logger.warning(f"Could not find snapshot table for {symbol}")
            return None

        # Parse all metrics from the table
        metrics = self._parse_snapshot_table(snapshot_table)

        # Extract sector/industry info
        sector_info = self._extract_sector_info(soup)

        return FinvizData(
            symbol=symbol,
            sector=sector_info.get('sector', 'Unknown'),
            industry=sector_info.get('industry', 'Unknown'),
            country=sector_info.get('country', 'USA'),
            market_cap=metrics.get('Market Cap', 'N/A'),
            pe_ratio=self._parse_float(metrics.get('P/E')),
            forward_pe=self._parse_float(metrics.get('Forward P/E')),
            peg_ratio=self._parse_float(metrics.get('PEG')),
            price_to_sales=self._parse_float(metrics.get('P/S')),
            price_to_book=self._parse_float(metrics.get('P/B')),
            eps_ttm=self._parse_float(metrics.get('EPS (ttm)')),
            eps_next_year=self._parse_float(metrics.get('EPS next Y')),
            eps_growth=self._parse_percent(metrics.get('EPS next Y', '').replace('%', '')),
            short_float=self._parse_percent(metrics.get('Short Float')),
            target_price=self._parse_float(metrics.get('Target Price')),
            recommendation=self._parse_float(metrics.get('Recom')),
            insider_own=self._parse_percent(metrics.get('Insider Own')),
            insider_trans=metrics.get('Insider Trans'),
            inst_own=self._parse_percent(metrics.get('Inst Own')),
            rsi_14=self._parse_float(metrics.get('RSI (14)')),
            sma20_dist=self._parse_percent(metrics.get('SMA20')),
            sma50_dist=self._parse_percent(metrics.get('SMA50')),
            sma200_dist=self._parse_percent(metrics.get('SMA200')),
            rel_volume=self._parse_float(metrics.get('Rel Volume')),
            avg_volume=metrics.get('Avg Volume'),
            price=self._parse_float(metrics.get('Price')),
            change=self._parse_percent(metrics.get('Change')),
        )

    def _parse_snapshot_table(self, table) -> Dict[str, str]:
        """
        Parse the FINVIZ snapshot table into key-value pairs.

        The table uses label-value pairs in alternating cells.
        """
        metrics = {}
        rows = table.find_all('tr')

        for row in rows:
            cells = row.find_all('td')
            # Process pairs of cells (label, value)
            for i in range(0, len(cells) - 1, 2):
                label_cell = cells[i]
                value_cell = cells[i + 1]

                label = label_cell.get_text(strip=True)
                value = value_cell.get_text(strip=True)

                if label:
                    metrics[label] = value

        return metrics

    def _extract_sector_info(self, soup) -> Dict[str, str]:
        """Extract sector, industry, and country from page header."""
        info = {}

        # Look for the fullview-title div
        title_div = soup.find('div', class_='fullview-title')
        if title_div:
            links = title_div.find_all('a')
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)

                if 'sec_' in href:
                    info['sector'] = text
                elif 'ind_' in href:
                    info['industry'] = text
                elif 'geo_' in href:
                    info['country'] = text

        return info

    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """
        Parse string to float, handling special characters.

        Handles: commas, percentage signs, dashes, currency symbols
        """
        if not value or value == '-' or value == 'N/A':
            return None

        try:
            # Remove commas, percentage signs, dollar signs
            cleaned = re.sub(r'[,%$]', '', value)
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _parse_percent(self, value: Optional[str]) -> Optional[float]:
        """Parse percentage string to float (as percentage value)."""
        if not value or value == '-' or value == 'N/A':
            return None

        try:
            # Remove percentage sign and commas
            cleaned = re.sub(r'[,%]', '', value)
            return float(cleaned)
        except (ValueError, TypeError):
            return None
