"""
Recommendation engine.

Generates final trading recommendations from aggregated signals.
Applies threshold logic to convert scores into actionable recommendations.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from .signal_aggregator import AggregatedSignals, SignalDirection


class RecommendationType(Enum):
    """Types of trading recommendations."""
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG SELL"


@dataclass
class Recommendation:
    """Final recommendation for a symbol."""

    symbol: str
    recommendation: RecommendationType
    confidence: float  # 0.0 to 1.0
    current_price: Optional[float]
    price_target: Optional[float]
    stop_loss: Optional[float]
    rationale: str
    key_signals: List[str]
    risks: List[str]
    signal_summary: Dict[str, int]

    @property
    def confidence_level(self) -> str:
        """Human-readable confidence level."""
        if self.confidence >= 0.7:
            return "High"
        elif self.confidence >= 0.5:
            return "Medium"
        else:
            return "Low"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'symbol': self.symbol,
            'recommendation': self.recommendation.value,
            'confidence': f"{self.confidence * 100:.0f}%",
            'confidence_level': self.confidence_level,
            'current_price': f"${self.current_price:.2f}" if self.current_price else "N/A",
            'price_target': f"${self.price_target:.2f}" if self.price_target else "N/A",
            'stop_loss': f"${self.stop_loss:.2f}" if self.stop_loss else "N/A",
            'rationale': self.rationale,
            'key_signals': self.key_signals,
            'risks': self.risks,
            'signal_summary': self.signal_summary,
        }


class RecommendationEngine:
    """
    Generates final trading recommendations from aggregated signals.

    Recommendation Thresholds:
    - STRONG BUY:  net_score >= 0.6 AND confidence >= 0.7
    - BUY:         net_score >= 0.3 AND confidence >= 0.5
    - HOLD:        -0.3 < net_score < 0.3 OR confidence < 0.5
    - SELL:        net_score <= -0.3 AND confidence >= 0.5
    - STRONG SELL: net_score <= -0.6 AND confidence >= 0.7
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the recommendation engine.

        Args:
            config: Configuration dictionary with threshold overrides
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # Configurable thresholds
        self.strong_threshold = config.get('strong_threshold', 0.6)
        self.moderate_threshold = config.get('moderate_threshold', 0.3)
        self.min_confidence = config.get('min_confidence', 0.5)
        self.high_confidence = config.get('high_confidence', 0.7)

    def generate_recommendations(
        self,
        aggregated_signals: Dict[str, AggregatedSignals],
        price_data: Dict[str, Any],
    ) -> Dict[str, Recommendation]:
        """
        Generate recommendations for all symbols.

        Args:
            aggregated_signals: Output from SignalAggregator
            price_data: Current price data from Yahoo Finance

        Returns:
            Dictionary mapping symbols to Recommendation objects
        """
        recommendations = {}

        for symbol, signals in aggregated_signals.items():
            rec = self._generate_single_recommendation(
                symbol, signals, price_data.get(symbol)
            )
            recommendations[symbol] = rec

        return recommendations

    def _generate_single_recommendation(
        self,
        symbol: str,
        signals: AggregatedSignals,
        price_data: Optional[Any],
    ) -> Recommendation:
        """Generate recommendation for a single symbol."""
        net_score = signals.net_score
        confidence = signals.confidence

        # Determine recommendation type
        rec_type = self._determine_recommendation_type(net_score, confidence)

        # Get current price
        current_price = None
        if price_data:
            current_price = getattr(price_data, 'current_price', None)

        # Calculate price targets
        price_target, stop_loss = self._calculate_price_targets(
            current_price, rec_type, signals
        )

        # Generate rationale
        rationale = self._generate_rationale(signals, rec_type)

        # Extract key signals (top 5)
        key_signals = self._extract_key_signals(signals)

        # Identify risks
        risks = self._identify_risks(signals, rec_type)

        return Recommendation(
            symbol=symbol,
            recommendation=rec_type,
            confidence=confidence,
            current_price=current_price,
            price_target=price_target,
            stop_loss=stop_loss,
            rationale=rationale,
            key_signals=key_signals,
            risks=risks,
            signal_summary=signals.signal_count,
        )

    def _determine_recommendation_type(
        self, net_score: float, confidence: float
    ) -> RecommendationType:
        """Determine recommendation based on score and confidence."""
        # Low confidence = HOLD regardless of score
        if confidence < self.min_confidence:
            return RecommendationType.HOLD

        # High confidence bullish
        if net_score >= self.strong_threshold and confidence >= self.high_confidence:
            return RecommendationType.STRONG_BUY

        # Moderate bullish
        if net_score >= self.moderate_threshold:
            return RecommendationType.BUY

        # High confidence bearish
        if net_score <= -self.strong_threshold and confidence >= self.high_confidence:
            return RecommendationType.STRONG_SELL

        # Moderate bearish
        if net_score <= -self.moderate_threshold:
            return RecommendationType.SELL

        # Everything else
        return RecommendationType.HOLD

    def _calculate_price_targets(
        self,
        current_price: Optional[float],
        rec_type: RecommendationType,
        signals: AggregatedSignals,
    ) -> tuple:
        """Calculate price target and stop loss based on recommendation."""
        if not current_price:
            return None, None

        # Base target percentages
        targets = {
            RecommendationType.STRONG_BUY: (0.10, -0.05),   # +10% target, -5% stop
            RecommendationType.BUY: (0.05, -0.03),          # +5% target, -3% stop
            RecommendationType.HOLD: (None, None),          # No targets
            RecommendationType.SELL: (-0.05, 0.03),         # -5% target, +3% stop
            RecommendationType.STRONG_SELL: (-0.10, 0.05),  # -10% target, +5% stop
        }

        target_pct, stop_pct = targets.get(rec_type, (None, None))

        if target_pct is None:
            return None, None

        price_target = current_price * (1 + target_pct)
        stop_loss = current_price * (1 + stop_pct)

        return price_target, stop_loss

    def _generate_rationale(
        self, signals: AggregatedSignals, rec_type: RecommendationType
    ) -> str:
        """Generate human-readable rationale."""
        bullish_signals = [
            s for s in signals.signals if s.direction == SignalDirection.BULLISH
        ]
        bearish_signals = [
            s for s in signals.signals if s.direction == SignalDirection.BEARISH
        ]

        parts = []

        if rec_type in [RecommendationType.STRONG_BUY, RecommendationType.BUY]:
            parts.append(f"{len(bullish_signals)} bullish signal(s) detected")
            if bullish_signals:
                top_signal = max(bullish_signals, key=lambda s: s.strength)
                parts.append(f"Key signal: {top_signal.details}")
            if bearish_signals:
                parts.append(f"({len(bearish_signals)} bearish signal(s) noted)")

        elif rec_type in [RecommendationType.STRONG_SELL, RecommendationType.SELL]:
            parts.append(f"{len(bearish_signals)} bearish signal(s) detected")
            if bearish_signals:
                top_signal = max(bearish_signals, key=lambda s: s.strength)
                parts.append(f"Key signal: {top_signal.details}")
            if bullish_signals:
                parts.append(f"({len(bullish_signals)} bullish signal(s) noted)")

        else:  # HOLD
            parts.append("Mixed or insufficient signals")
            parts.append(
                f"Bullish: {len(bullish_signals)}, Bearish: {len(bearish_signals)}"
            )

        return ". ".join(parts) + "."

    def _extract_key_signals(self, signals: AggregatedSignals) -> List[str]:
        """Extract top 5 most important signals."""
        # Sort by strength
        sorted_signals = sorted(
            signals.signals, key=lambda s: s.strength, reverse=True
        )
        return [s.details for s in sorted_signals[:5]]

    def _identify_risks(
        self, signals: AggregatedSignals, rec_type: RecommendationType
    ) -> List[str]:
        """Identify key risks for the recommendation."""
        risks = []

        bullish = signals.signal_count['bullish']
        bearish = signals.signal_count['bearish']

        # Conflicting signals risk
        if rec_type in [RecommendationType.STRONG_BUY, RecommendationType.BUY]:
            if bearish > 0:
                risks.append(
                    f"{bearish} bearish signal(s) present - monitor closely"
                )

        if rec_type in [RecommendationType.STRONG_SELL, RecommendationType.SELL]:
            if bullish > 0:
                risks.append(
                    f"{bullish} bullish signal(s) present - watch for reversal"
                )

        # Low confidence warning
        if signals.confidence < 0.6:
            risks.append("Lower confidence due to mixed or limited signals")

        # Check for extreme conditions
        for sig in signals.signals:
            details_lower = sig.details.lower()
            if 'overbought' in details_lower:
                risks.append("Overbought conditions - potential pullback")
            if 'oversold' in details_lower:
                risks.append("Oversold conditions - high volatility expected")

        if not risks:
            risks.append("Standard market risks apply")

        return risks[:4]  # Limit to 4 risks
