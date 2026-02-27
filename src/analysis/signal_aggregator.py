"""
Signal aggregation engine.

Combines signals from multiple data sources into unified analysis.
Each signal is weighted based on source reliability and signal type.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SignalDirection(Enum):
    """Direction of a trading signal."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class Signal:
    """Individual signal from a data source."""

    source: str
    signal_type: str  # e.g., 'RSI', 'MACD', 'Pattern', 'Insider'
    direction: SignalDirection
    strength: float  # 0.0 to 1.0
    details: str
    weight: float = 1.0  # Will be calculated based on config


@dataclass
class AggregatedSignals:
    """Collection of signals for a symbol."""

    symbol: str
    signals: List[Signal] = field(default_factory=list)
    bullish_score: float = 0.0
    bearish_score: float = 0.0
    total_weight: float = 0.0

    @property
    def net_score(self) -> float:
        """Net score from -1 (bearish) to +1 (bullish)."""
        if self.total_weight == 0:
            return 0.0
        return (self.bullish_score - self.bearish_score) / self.total_weight

    @property
    def confidence(self) -> float:
        """Confidence level based on signal agreement."""
        if not self.signals:
            return 0.0

        bullish_count = sum(
            1 for s in self.signals if s.direction == SignalDirection.BULLISH
        )
        bearish_count = sum(
            1 for s in self.signals if s.direction == SignalDirection.BEARISH
        )

        total = len(self.signals)
        max_agreement = max(bullish_count, bearish_count)

        return max_agreement / total if total > 0 else 0.0

    @property
    def signal_count(self) -> Dict[str, int]:
        """Count of signals by direction."""
        return {
            'bullish': sum(1 for s in self.signals if s.direction == SignalDirection.BULLISH),
            'bearish': sum(1 for s in self.signals if s.direction == SignalDirection.BEARISH),
            'neutral': sum(1 for s in self.signals if s.direction == SignalDirection.NEUTRAL),
        }


class SignalAggregator:
    """
    Aggregates signals from multiple data sources with configurable weights.

    Default source weights:
    - Yahoo Finance (price/technicals): 1.0 (base reference)
    - FINVIZ (fundamentals/insider): 0.8
    - Investing.com (futures): 0.6 (secondary confirmation)
    - Pattern Analysis: 0.7
    """

    DEFAULT_SOURCE_WEIGHTS = {
        'Yahoo Finance': 1.0,
        'FINVIZ': 0.8,
        'Investing.com': 0.6,
        'StockCharts / Pattern Analysis': 0.7,
    }

    DEFAULT_SIGNAL_WEIGHTS = {
        'RSI': 0.8,
        'MACD': 0.9,
        'SMA_Cross': 1.0,
        'Volume': 0.6,
        'Pattern': 0.7,
        'Insider': 0.5,
        'Analyst_Target': 0.4,
        'Futures_Trend': 0.6,
        'Trend': 0.7,
        'Breakout': 0.8,
        'Support_Resistance': 0.6,
    }

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the signal aggregator.

        Args:
            config: Configuration dictionary with optional weight overrides
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # Allow config override of weights
        self.source_weights = config.get(
            'source_weights', self.DEFAULT_SOURCE_WEIGHTS
        )
        self.signal_weights = config.get(
            'signal_type_weights', self.DEFAULT_SIGNAL_WEIGHTS
        )

    def aggregate(
        self,
        yahoo_data: Dict[str, Any],
        finviz_data: Dict[str, Any],
        investing_data: Dict[str, Any],
        pattern_data: Dict[str, Any],
        symbols: List[str],
    ) -> Dict[str, AggregatedSignals]:
        """
        Aggregate signals from all sources for each symbol.

        Args:
            yahoo_data: Data from Yahoo Finance scraper
            finviz_data: Data from FINVIZ scraper
            investing_data: Data from Investing.com scraper
            pattern_data: Data from pattern detector
            symbols: List of symbols to aggregate

        Returns:
            Dictionary mapping symbols to AggregatedSignals
        """
        results = {}

        for symbol in symbols:
            aggregated = AggregatedSignals(symbol=symbol)

            # Process Yahoo Finance signals
            if symbol in yahoo_data:
                signals = self._extract_yahoo_signals(yahoo_data[symbol], symbol)
                self._add_signals(aggregated, signals)

            # Process FINVIZ signals
            if symbol in finviz_data:
                signals = self._extract_finviz_signals(
                    finviz_data[symbol], yahoo_data.get(symbol), symbol
                )
                self._add_signals(aggregated, signals)

            # Process pattern signals
            if symbol in pattern_data:
                signals = self._extract_pattern_signals(pattern_data[symbol], symbol)
                self._add_signals(aggregated, signals)

            # Process futures context (affects all equities)
            if investing_data:
                signals = self._extract_futures_context(investing_data)
                self._add_signals(aggregated, signals)

            results[symbol] = aggregated

        return results

    def _add_signals(
        self, aggregated: AggregatedSignals, signals: List[Signal]
    ) -> None:
        """Add signals to aggregated result and update scores."""
        for signal in signals:
            aggregated.signals.append(signal)

            # Calculate weighted contribution
            source_weight = self.source_weights.get(signal.source, 1.0)
            type_weight = self.signal_weights.get(signal.signal_type, 1.0)
            total_weight = signal.strength * source_weight * type_weight

            aggregated.total_weight += total_weight

            if signal.direction == SignalDirection.BULLISH:
                aggregated.bullish_score += total_weight
            elif signal.direction == SignalDirection.BEARISH:
                aggregated.bearish_score += total_weight

    def _extract_yahoo_signals(self, data, symbol: str) -> List[Signal]:
        """Extract signals from Yahoo Finance data."""
        signals = []
        source = "Yahoo Finance"

        # RSI Signal
        if data.rsi_14 is not None:
            if data.rsi_14 < 30:
                signals.append(Signal(
                    source=source,
                    signal_type='RSI',
                    direction=SignalDirection.BULLISH,
                    strength=0.8,
                    details=f"RSI oversold at {data.rsi_14:.1f}",
                ))
            elif data.rsi_14 > 70:
                signals.append(Signal(
                    source=source,
                    signal_type='RSI',
                    direction=SignalDirection.BEARISH,
                    strength=0.8,
                    details=f"RSI overbought at {data.rsi_14:.1f}",
                ))
            elif data.rsi_14 < 45:
                signals.append(Signal(
                    source=source,
                    signal_type='RSI',
                    direction=SignalDirection.BULLISH,
                    strength=0.4,
                    details=f"RSI below neutral at {data.rsi_14:.1f}",
                ))
            elif data.rsi_14 > 55:
                signals.append(Signal(
                    source=source,
                    signal_type='RSI',
                    direction=SignalDirection.BEARISH,
                    strength=0.4,
                    details=f"RSI above neutral at {data.rsi_14:.1f}",
                ))

        # MACD Signal
        if data.macd_signal:
            direction = (
                SignalDirection.BULLISH
                if data.macd_signal == 'bullish'
                else SignalDirection.BEARISH
            )
            signals.append(Signal(
                source=source,
                signal_type='MACD',
                direction=direction,
                strength=0.7,
                details=f"MACD {data.macd_signal}",
            ))

        # SMA Cross Signals
        if data.sma_20 and data.current_price:
            price = data.current_price
            pct_from_sma20 = (price - data.sma_20) / data.sma_20 * 100

            if pct_from_sma20 > 2:
                signals.append(Signal(
                    source=source,
                    signal_type='SMA_Cross',
                    direction=SignalDirection.BULLISH,
                    strength=0.5,
                    details=f"Price {pct_from_sma20:.1f}% above SMA20",
                ))
            elif pct_from_sma20 < -2:
                signals.append(Signal(
                    source=source,
                    signal_type='SMA_Cross',
                    direction=SignalDirection.BEARISH,
                    strength=0.5,
                    details=f"Price {abs(pct_from_sma20):.1f}% below SMA20",
                ))

        # Golden/Death Cross (SMA50 vs SMA200)
        if data.sma_50 and data.sma_200:
            if data.sma_50 > data.sma_200:
                signals.append(Signal(
                    source=source,
                    signal_type='SMA_Cross',
                    direction=SignalDirection.BULLISH,
                    strength=0.6,
                    details="Golden Cross (SMA50 > SMA200)",
                ))
            else:
                signals.append(Signal(
                    source=source,
                    signal_type='SMA_Cross',
                    direction=SignalDirection.BEARISH,
                    strength=0.6,
                    details="Death Cross (SMA50 < SMA200)",
                ))

        # Volume Signal
        if data.volume and data.avg_volume and data.avg_volume > 0:
            volume_ratio = data.volume / data.avg_volume
            if volume_ratio > 1.5:
                direction = (
                    SignalDirection.BULLISH
                    if data.change_percent > 0
                    else SignalDirection.BEARISH
                )
                signals.append(Signal(
                    source=source,
                    signal_type='Volume',
                    direction=direction,
                    strength=0.5,
                    details=f"Volume {volume_ratio:.1f}x average",
                ))

        return signals

    def _extract_finviz_signals(
        self, data, yahoo_data, symbol: str
    ) -> List[Signal]:
        """Extract signals from FINVIZ data."""
        signals = []
        source = "FINVIZ"

        # Analyst Target Signal
        if data.target_price and yahoo_data and yahoo_data.current_price:
            current = yahoo_data.current_price
            target = data.target_price
            upside = (target - current) / current * 100

            if upside > 15:
                signals.append(Signal(
                    source=source,
                    signal_type='Analyst_Target',
                    direction=SignalDirection.BULLISH,
                    strength=0.5,
                    details=f"Analyst target ${target:.2f} ({upside:.0f}% upside)",
                ))
            elif upside < -10:
                signals.append(Signal(
                    source=source,
                    signal_type='Analyst_Target',
                    direction=SignalDirection.BEARISH,
                    strength=0.5,
                    details=f"Analyst target ${target:.2f} ({upside:.0f}% downside)",
                ))

        # Insider Activity Signal
        if data.insider_trans:
            trans = data.insider_trans.lower()
            if '+' in trans or 'buy' in trans:
                signals.append(Signal(
                    source=source,
                    signal_type='Insider',
                    direction=SignalDirection.BULLISH,
                    strength=0.7,
                    details=f"Insider buying: {data.insider_trans}",
                ))
            elif '-' in trans or 'sell' in trans:
                signals.append(Signal(
                    source=source,
                    signal_type='Insider',
                    direction=SignalDirection.BEARISH,
                    strength=0.5,
                    details=f"Insider selling: {data.insider_trans}",
                ))

        # SMA Distance Signals
        if data.sma200_dist is not None:
            if data.sma200_dist > 10:
                signals.append(Signal(
                    source=source,
                    signal_type='SMA_Cross',
                    direction=SignalDirection.BULLISH,
                    strength=0.5,
                    details=f"Price {data.sma200_dist:.1f}% above SMA200",
                ))
            elif data.sma200_dist < -10:
                signals.append(Signal(
                    source=source,
                    signal_type='SMA_Cross',
                    direction=SignalDirection.BEARISH,
                    strength=0.5,
                    details=f"Price {abs(data.sma200_dist):.1f}% below SMA200",
                ))

        # Relative Volume Signal
        if data.rel_volume and data.rel_volume > 1.5:
            direction = (
                SignalDirection.BULLISH
                if (data.change and data.change > 0)
                else SignalDirection.BEARISH
            )
            signals.append(Signal(
                source=source,
                signal_type='Volume',
                direction=direction,
                strength=0.4,
                details=f"Relative volume {data.rel_volume:.2f}x",
            ))

        return signals

    def _extract_pattern_signals(self, data, symbol: str) -> List[Signal]:
        """Extract signals from pattern analysis."""
        signals = []
        source = "StockCharts / Pattern Analysis"

        # Pattern Signal
        if data.pattern_name:
            direction_map = {
                'bullish': SignalDirection.BULLISH,
                'bearish': SignalDirection.BEARISH,
                'neutral': SignalDirection.NEUTRAL,
            }
            direction = direction_map.get(data.pattern_type, SignalDirection.NEUTRAL)

            signals.append(Signal(
                source=source,
                signal_type='Pattern',
                direction=direction,
                strength=data.confidence,
                details=f"Pattern: {data.pattern_name}",
            ))

        # Trend Signal
        if data.trend_direction != 'sideways':
            direction = (
                SignalDirection.BULLISH
                if data.trend_direction == 'up'
                else SignalDirection.BEARISH
            )
            signals.append(Signal(
                source=source,
                signal_type='Trend',
                direction=direction,
                strength=data.trend_strength,
                details=f"Trend: {data.trend_direction}",
            ))

        # Breakout Signal
        if data.breakout_signal:
            direction = (
                SignalDirection.BULLISH
                if 'bullish' in data.breakout_signal
                else SignalDirection.BEARISH
            )
            signals.append(Signal(
                source=source,
                signal_type='Breakout',
                direction=direction,
                strength=0.8,
                details=f"Breakout: {data.breakout_signal.replace('_', ' ')}",
            ))

        # Support/Resistance proximity
        if data.near_support:
            signals.append(Signal(
                source=source,
                signal_type='Support_Resistance',
                direction=SignalDirection.BULLISH,
                strength=0.5,
                details=f"Near support at ${data.support_level:.2f}",
            ))
        if data.near_resistance:
            signals.append(Signal(
                source=source,
                signal_type='Support_Resistance',
                direction=SignalDirection.BEARISH,
                strength=0.5,
                details=f"Near resistance at ${data.resistance_level:.2f}",
            ))

        return signals

    def _extract_futures_context(self, futures_data: Dict) -> List[Signal]:
        """Extract market context from futures data."""
        signals = []
        source = "Investing.com"

        # Count bullish/bearish futures
        bullish_count = 0
        bearish_count = 0
        details_parts = []

        for symbol, data in futures_data.items():
            change_pct = getattr(data, 'change_percent', 0)
            if change_pct > 0.3:
                bullish_count += 1
                details_parts.append(f"{symbol} +{change_pct:.1f}%")
            elif change_pct < -0.3:
                bearish_count += 1
                details_parts.append(f"{symbol} {change_pct:.1f}%")

        if bullish_count > bearish_count and bullish_count >= 2:
            signals.append(Signal(
                source=source,
                signal_type='Futures_Trend',
                direction=SignalDirection.BULLISH,
                strength=0.5,
                details=f"Futures bullish: {', '.join(details_parts[:3])}",
            ))
        elif bearish_count > bullish_count and bearish_count >= 2:
            signals.append(Signal(
                source=source,
                signal_type='Futures_Trend',
                direction=SignalDirection.BEARISH,
                strength=0.5,
                details=f"Futures bearish: {', '.join(details_parts[:3])}",
            ))

        return signals
