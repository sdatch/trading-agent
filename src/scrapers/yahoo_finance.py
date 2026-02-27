"""
Yahoo Finance data scraper using yfinance library.

This is the primary data source and provides:
- Current price and volume data
- Historical prices for technical calculations
- Basic company info
- Futures data (ES=F, NQ=F, YM=F, CL=F, GC=F)
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from .base_scraper import BaseScraper


@dataclass
class StockData:
    """Data container for stock information."""

    symbol: str
    current_price: float
    previous_close: float
    open_price: float
    day_high: float
    day_low: float
    change_percent: float
    volume: int
    avg_volume: int
    fifty_two_week_high: float
    fifty_two_week_low: float
    market_cap: Optional[float]
    pe_ratio: Optional[float]
    sma_20: Optional[float]
    sma_50: Optional[float]
    sma_200: Optional[float]
    rsi_14: Optional[float]
    macd_signal: Optional[str]  # 'bullish', 'bearish', or None


@dataclass
class FuturesData:
    """Data container for futures contract information."""

    symbol: str
    name: str
    current_price: float
    change: float
    change_percent: float
    day_high: float
    day_low: float
    volume: int


class YahooFinanceScraper(BaseScraper):
    """
    Scraper for Yahoo Finance data using yfinance library.

    This is the most reliable data source and should be primary.
    """

    # Yahoo Finance symbols for futures
    FUTURES_SYMBOLS = {
        'ES': 'ES=F',   # S&P 500 E-mini
        'NQ': 'NQ=F',   # NASDAQ E-mini
        'YM': 'YM=F',   # Dow E-mini
        'RTY': 'RTY=F', # Russell 2000 E-mini
        'CL': 'CL=F',   # Crude Oil WTI
        'GC': 'GC=F',   # Gold
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
        self._min_request_interval = config.get('rate_limit_seconds', 0.5)

    def get_source_name(self) -> str:
        return "Yahoo Finance"

    def fetch_data(self, symbols: List[str]) -> Dict[str, StockData]:
        """
        Fetch stock data for multiple symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary mapping symbols to StockData objects
        """
        results = {}

        for symbol in symbols:
            try:
                self._rate_limit()
                data = self._fetch_single_stock(symbol)
                if data:
                    results[symbol] = data
            except Exception as e:
                self.logger.error(f"Failed to fetch {symbol}: {e}")
                continue

        return results

    def fetch_futures_data(
        self, contracts: Optional[List[str]] = None
    ) -> Dict[str, FuturesData]:
        """
        Fetch futures data for specified contracts.

        Args:
            contracts: List of contract codes (ES, NQ, YM) or None for defaults

        Returns:
            Dictionary mapping contract codes to FuturesData objects
        """
        if contracts is None:
            contracts = ['ES', 'NQ', 'YM']

        results = {}

        for contract in contracts:
            try:
                self._rate_limit()
                data = self._fetch_single_futures(contract)
                if data:
                    results[contract] = data
            except Exception as e:
                self.logger.error(f"Failed to fetch futures {contract}: {e}")
                continue

        return results

    def _fetch_single_stock(self, symbol: str) -> Optional[StockData]:
        """Fetch data for a single stock symbol."""
        ticker = yf.Ticker(symbol)

        # Get current info
        try:
            info = ticker.info
        except Exception as e:
            self.logger.warning(f"Failed to get info for {symbol}: {e}")
            info = {}

        # Get historical data for technical calculations
        try:
            hist = ticker.history(period="6mo", interval="1d")
        except Exception as e:
            self.logger.warning(f"Failed to get history for {symbol}: {e}")
            hist = pd.DataFrame()

        if hist.empty and not info:
            self.logger.warning(f"No data available for {symbol}")
            return None

        # Extract current price (try multiple sources)
        current_price = (
            info.get('currentPrice') or
            info.get('regularMarketPrice') or
            (hist['Close'].iloc[-1] if not hist.empty else 0)
        )

        if not current_price:
            self.logger.warning(f"No price data for {symbol}")
            return None

        # Calculate technical indicators
        sma_20 = sma_50 = sma_200 = rsi_14 = macd_signal = None

        if not hist.empty and len(hist) >= 14:
            closes = hist['Close']

            if len(closes) >= 20:
                sma_20 = closes.rolling(window=20).mean().iloc[-1]
            if len(closes) >= 50:
                sma_50 = closes.rolling(window=50).mean().iloc[-1]
            if len(closes) >= 200:
                sma_200 = closes.rolling(window=200).mean().iloc[-1]

            rsi_14 = self._calculate_rsi(closes, 14)
            macd_signal = self._calculate_macd_signal(closes)

        return StockData(
            symbol=symbol,
            current_price=float(current_price),
            previous_close=float(info.get('previousClose', 0) or 0),
            open_price=float(info.get('open', 0) or 0),
            day_high=float(info.get('dayHigh', 0) or 0),
            day_low=float(info.get('dayLow', 0) or 0),
            change_percent=float(info.get('regularMarketChangePercent', 0) or 0),
            volume=int(info.get('volume', 0) or 0),
            avg_volume=int(info.get('averageVolume', 0) or 0),
            fifty_two_week_high=float(info.get('fiftyTwoWeekHigh', 0) or 0),
            fifty_two_week_low=float(info.get('fiftyTwoWeekLow', 0) or 0),
            market_cap=info.get('marketCap'),
            pe_ratio=info.get('trailingPE'),
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi_14=rsi_14,
            macd_signal=macd_signal,
        )

    def _fetch_single_futures(self, contract: str) -> Optional[FuturesData]:
        """Fetch data for a single futures contract."""
        yahoo_symbol = self.FUTURES_SYMBOLS.get(contract, f"{contract}=F")
        name = self.FUTURES_NAMES.get(contract, contract)

        ticker = yf.Ticker(yahoo_symbol)

        try:
            info = ticker.info
        except Exception as e:
            self.logger.warning(f"Failed to get info for futures {contract}: {e}")
            return None

        current_price = info.get('regularMarketPrice') or info.get('previousClose')

        if not current_price:
            self.logger.warning(f"No price data for futures {contract}")
            return None

        previous_close = info.get('previousClose', current_price)
        change = current_price - previous_close
        change_percent = (change / previous_close * 100) if previous_close else 0

        return FuturesData(
            symbol=contract,
            name=name,
            current_price=float(current_price),
            change=float(change),
            change_percent=float(change_percent),
            day_high=float(info.get('dayHigh', current_price) or current_price),
            day_low=float(info.get('dayLow', current_price) or current_price),
            volume=int(info.get('volume', 0) or 0),
        )

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> Optional[float]:
        """
        Calculate the Relative Strength Index (RSI).

        Args:
            prices: Series of closing prices
            period: RSI period (default 14)

        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(prices) < period + 1:
            return None

        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        # Avoid division by zero
        rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else 100
        rsi = 100 - (100 / (1 + rs))

        return float(rsi)

    def _calculate_macd_signal(self, prices: pd.Series) -> Optional[str]:
        """
        Calculate MACD and determine signal direction.

        Args:
            prices: Series of closing prices

        Returns:
            'bullish', 'bearish', or None
        """
        if len(prices) < 26:
            return None

        # Calculate MACD components
        ema_12 = prices.ewm(span=12, adjust=False).mean()
        ema_26 = prices.ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()

        # Current values
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]

        # Detect crossover
        if current_macd > current_signal and prev_macd <= prev_signal:
            return 'bullish'  # Bullish crossover
        elif current_macd < current_signal and prev_macd >= prev_signal:
            return 'bearish'  # Bearish crossover
        elif current_macd > current_signal:
            return 'bullish'
        else:
            return 'bearish'
