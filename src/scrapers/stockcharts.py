"""
Chart pattern detection using local computation.

Instead of scraping StockCharts.com (which has anti-bot measures),
this module computes chart patterns locally using price data from yfinance.

Detects:
- Double Top / Double Bottom
- Support and Resistance levels
- Trend direction
- Breakouts and Breakdowns
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class PatternData:
    """Data container for chart pattern analysis."""

    symbol: str
    pattern_name: Optional[str]
    pattern_type: str  # 'bullish', 'bearish', 'neutral'
    confidence: float  # 0.0 to 1.0
    support_level: Optional[float]
    resistance_level: Optional[float]
    trend_direction: str  # 'up', 'down', 'sideways'
    trend_strength: float  # 0.0 to 1.0
    near_support: bool
    near_resistance: bool
    breakout_signal: Optional[str]  # 'bullish_breakout', 'bearish_breakdown', None


class ChartPatternDetector:
    """
    Local chart pattern detection using price data.

    Analyzes price history to detect patterns and key levels.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the pattern detector.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.lookback_days = config.get('pattern_lookback_days', 60)

    def get_source_name(self) -> str:
        return "StockCharts / Pattern Analysis"

    def fetch_data(self, symbols: List[str]) -> Dict[str, PatternData]:
        """
        Analyze patterns for multiple symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary mapping symbols to PatternData objects
        """
        results = {}

        for symbol in symbols:
            try:
                pattern_data = self._analyze_symbol(symbol)
                if pattern_data:
                    results[symbol] = pattern_data
            except Exception as e:
                self.logger.error(f"Pattern analysis failed for {symbol}: {e}")
                continue

        return results

    def _analyze_symbol(self, symbol: str) -> Optional[PatternData]:
        """Analyze patterns for a single symbol."""
        # Fetch price data from yfinance
        ticker = yf.Ticker(symbol)

        try:
            hist = ticker.history(period="3mo", interval="1d")
        except Exception as e:
            self.logger.warning(f"Failed to get history for {symbol}: {e}")
            return None

        if hist.empty or len(hist) < 20:
            self.logger.warning(f"Insufficient data for {symbol}")
            return None

        return self.analyze_patterns(hist, symbol)

    def analyze_patterns(self, price_data: pd.DataFrame, symbol: str) -> PatternData:
        """
        Analyze price data for chart patterns.

        Args:
            price_data: DataFrame with OHLCV columns
            symbol: Stock symbol

        Returns:
            PatternData object with analysis results
        """
        if len(price_data) < 20:
            return PatternData(
                symbol=symbol,
                pattern_name=None,
                pattern_type='neutral',
                confidence=0.0,
                support_level=None,
                resistance_level=None,
                trend_direction='sideways',
                trend_strength=0.0,
                near_support=False,
                near_resistance=False,
                breakout_signal=None,
            )

        # Calculate support and resistance
        support, resistance = self._find_support_resistance(price_data)

        # Detect trend
        trend, trend_strength = self._detect_trend(price_data)

        # Look for specific patterns
        pattern_name, pattern_type, confidence = self._detect_patterns(price_data)

        # Check proximity to support/resistance
        current_price = price_data['Close'].iloc[-1]
        near_support = self._is_near_level(current_price, support, tolerance=0.02)
        near_resistance = self._is_near_level(current_price, resistance, tolerance=0.02)

        # Check for breakouts
        breakout_signal = self._detect_breakout(price_data, support, resistance)

        return PatternData(
            symbol=symbol,
            pattern_name=pattern_name,
            pattern_type=pattern_type,
            confidence=confidence,
            support_level=support,
            resistance_level=resistance,
            trend_direction=trend,
            trend_strength=trend_strength,
            near_support=near_support,
            near_resistance=near_resistance,
            breakout_signal=breakout_signal,
        )

    def _find_support_resistance(
        self, df: pd.DataFrame
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Find key support and resistance levels.

        Uses recent local minima/maxima and common price levels.
        """
        closes = df['Close'].values
        highs = df['High'].values
        lows = df['Low'].values

        window = min(20, len(closes) // 3)

        # Recent trading range
        recent_high = np.max(highs[-window:])
        recent_low = np.min(lows[-window:])

        # Find swing lows for support
        swing_lows = self._find_swing_lows(lows, order=5)
        support = np.mean(swing_lows[-3:]) if len(swing_lows) >= 3 else recent_low

        # Find swing highs for resistance
        swing_highs = self._find_swing_highs(highs, order=5)
        resistance = np.mean(swing_highs[-3:]) if len(swing_highs) >= 3 else recent_high

        return float(support), float(resistance)

    def _detect_trend(self, df: pd.DataFrame) -> Tuple[str, float]:
        """
        Detect overall trend direction and strength.

        Returns:
            Tuple of (direction, strength)
            - direction: 'up', 'down', or 'sideways'
            - strength: 0.0 to 1.0
        """
        closes = df['Close'].values

        if len(closes) < 20:
            return 'sideways', 0.0

        # Calculate 20-day SMA
        sma20 = df['Close'].rolling(window=20).mean()

        # Price relative to SMA
        current_price = closes[-1]
        current_sma = sma20.iloc[-1]
        sma_diff_pct = (current_price - current_sma) / current_sma

        # SMA slope (trend direction)
        if len(sma20) >= 10:
            sma_slope = (sma20.iloc[-1] - sma20.iloc[-10]) / sma20.iloc[-10]
        else:
            sma_slope = 0

        # Determine trend
        if sma_slope > 0.03 and sma_diff_pct > 0.01:
            return 'up', min(abs(sma_slope) * 10, 1.0)
        elif sma_slope < -0.03 and sma_diff_pct < -0.01:
            return 'down', min(abs(sma_slope) * 10, 1.0)
        else:
            return 'sideways', 0.3

    def _detect_patterns(
        self, df: pd.DataFrame
    ) -> Tuple[Optional[str], str, float]:
        """
        Detect specific chart patterns.

        Returns:
            Tuple of (pattern_name, pattern_type, confidence)
        """
        highs = df['High'].values
        lows = df['Low'].values
        closes = df['Close'].values

        # Check for double top
        if self._is_double_top(highs, closes):
            return ('Double Top', 'bearish', 0.7)

        # Check for double bottom
        if self._is_double_bottom(lows, closes):
            return ('Double Bottom', 'bullish', 0.7)

        # Check for higher highs and higher lows (uptrend)
        if self._is_higher_highs_lows(highs, lows):
            return ('Higher Highs/Lows', 'bullish', 0.6)

        # Check for lower highs and lower lows (downtrend)
        if self._is_lower_highs_lows(highs, lows):
            return ('Lower Highs/Lows', 'bearish', 0.6)

        return (None, 'neutral', 0.0)

    def _is_double_top(
        self, highs: np.ndarray, closes: np.ndarray, tolerance: float = 0.02
    ) -> bool:
        """Detect double top pattern."""
        if len(highs) < 30:
            return False

        # Find peaks in recent data
        peak_indices = self._find_peak_indices(highs[-30:], order=5)

        if len(peak_indices) >= 2:
            peak1 = highs[-30:][peak_indices[-1]]
            peak2 = highs[-30:][peak_indices[-2]]

            # Peaks should be within tolerance
            if abs(peak1 - peak2) / peak1 < tolerance:
                # Current price should be below both peaks
                if closes[-1] < peak1 * 0.98:
                    return True

        return False

    def _is_double_bottom(
        self, lows: np.ndarray, closes: np.ndarray, tolerance: float = 0.02
    ) -> bool:
        """Detect double bottom pattern."""
        if len(lows) < 30:
            return False

        # Find troughs in recent data
        trough_indices = self._find_trough_indices(lows[-30:], order=5)

        if len(trough_indices) >= 2:
            trough1 = lows[-30:][trough_indices[-1]]
            trough2 = lows[-30:][trough_indices[-2]]

            # Troughs should be within tolerance
            if abs(trough1 - trough2) / trough1 < tolerance:
                # Current price should be above both troughs
                if closes[-1] > trough1 * 1.02:
                    return True

        return False

    def _is_higher_highs_lows(
        self, highs: np.ndarray, lows: np.ndarray
    ) -> bool:
        """Check for pattern of higher highs and higher lows."""
        if len(highs) < 20:
            return False

        # Compare recent periods
        period1_high = np.max(highs[-20:-10])
        period2_high = np.max(highs[-10:])
        period1_low = np.min(lows[-20:-10])
        period2_low = np.min(lows[-10:])

        return period2_high > period1_high and period2_low > period1_low

    def _is_lower_highs_lows(
        self, highs: np.ndarray, lows: np.ndarray
    ) -> bool:
        """Check for pattern of lower highs and lower lows."""
        if len(highs) < 20:
            return False

        # Compare recent periods
        period1_high = np.max(highs[-20:-10])
        period2_high = np.max(highs[-10:])
        period1_low = np.min(lows[-20:-10])
        period2_low = np.min(lows[-10:])

        return period2_high < period1_high and period2_low < period1_low

    def _detect_breakout(
        self,
        df: pd.DataFrame,
        support: Optional[float],
        resistance: Optional[float],
    ) -> Optional[str]:
        """Detect breakout or breakdown from key levels."""
        if len(df) < 2:
            return None

        current_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]

        # Check for bullish breakout above resistance
        if resistance and current_close > resistance and prev_close <= resistance:
            return 'bullish_breakout'

        # Check for bearish breakdown below support
        if support and current_close < support and prev_close >= support:
            return 'bearish_breakdown'

        return None

    def _is_near_level(
        self, price: float, level: Optional[float], tolerance: float = 0.02
    ) -> bool:
        """Check if price is near a support/resistance level."""
        if level is None:
            return False
        return abs(price - level) / level < tolerance

    def _find_swing_lows(self, data: np.ndarray, order: int = 5) -> List[float]:
        """Find swing low values."""
        swing_lows = []
        for i in range(order, len(data) - order):
            if all(data[i] <= data[i - j] for j in range(1, order + 1)) and \
               all(data[i] <= data[i + j] for j in range(1, order + 1)):
                swing_lows.append(data[i])
        return swing_lows

    def _find_swing_highs(self, data: np.ndarray, order: int = 5) -> List[float]:
        """Find swing high values."""
        swing_highs = []
        for i in range(order, len(data) - order):
            if all(data[i] >= data[i - j] for j in range(1, order + 1)) and \
               all(data[i] >= data[i + j] for j in range(1, order + 1)):
                swing_highs.append(data[i])
        return swing_highs

    def _find_peak_indices(self, data: np.ndarray, order: int = 5) -> List[int]:
        """Find indices of local maxima."""
        peaks = []
        for i in range(order, len(data) - order):
            if all(data[i] > data[i - j] for j in range(1, order + 1)) and \
               all(data[i] > data[i + j] for j in range(1, order + 1)):
                peaks.append(i)
        return peaks

    def _find_trough_indices(self, data: np.ndarray, order: int = 5) -> List[int]:
        """Find indices of local minima."""
        troughs = []
        for i in range(order, len(data) - order):
            if all(data[i] < data[i - j] for j in range(1, order + 1)) and \
               all(data[i] < data[i + j] for j in range(1, order + 1)):
                troughs.append(i)
        return troughs
