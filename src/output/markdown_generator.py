"""
Markdown report generator.

Creates date-stamped markdown files with trading recommendations
following the format specified in the PRD.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..analysis.recommendation_engine import Recommendation, RecommendationType
from ..analysis.signal_aggregator import AggregatedSignals


class MarkdownGenerator:
    """
    Generates markdown reports for trading recommendations.

    Output format follows PRD specification:
    - trading-recommendations-YYYY-MM-DD.md
    """

    def __init__(self, output_dir: str = "./output"):
        """
        Initialize the markdown generator.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_report(
        self,
        recommendations: Dict[str, Recommendation],
        aggregated_signals: Dict[str, AggregatedSignals],
        collected_data: Dict[str, Any],
        execution_metrics: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Generate a markdown report.

        Args:
            recommendations: Dictionary of recommendations by symbol
            aggregated_signals: Dictionary of aggregated signals by symbol
            collected_data: Raw data from scrapers
            execution_metrics: Optional execution timing info

        Returns:
            Path to the generated report file
        """
        today = datetime.now()
        filename = f"trading-recommendations-{today.strftime('%Y-%m-%d')}.md"
        filepath = self.output_dir / filename

        content = self._build_report(
            recommendations,
            aggregated_signals,
            collected_data,
            execution_metrics,
            today,
        )

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        self.logger.info(f"Report generated: {filepath}")
        return filepath

    def _build_report(
        self,
        recommendations: Dict[str, Recommendation],
        aggregated_signals: Dict[str, AggregatedSignals],
        collected_data: Dict[str, Any],
        execution_metrics: Optional[Dict[str, Any]],
        timestamp: datetime,
    ) -> str:
        """Build the full markdown report content."""
        sections = []

        # Header
        sections.append(self._build_header(timestamp))

        # Market Overview
        sections.append(self._build_market_overview(collected_data))

        # Sort recommendations by confidence and type
        sorted_recs = self._sort_recommendations(recommendations)

        # High Confidence Recommendations
        high_conf = [r for r in sorted_recs if r.confidence >= 0.7]
        if high_conf:
            sections.append(self._build_recommendation_section(
                "High Confidence Recommendations", high_conf
            ))

        # Medium Confidence Recommendations
        medium_conf = [r for r in sorted_recs if 0.5 <= r.confidence < 0.7]
        if medium_conf:
            sections.append(self._build_recommendation_section(
                "Medium Confidence Recommendations", medium_conf
            ))

        # Watchlist (HOLD recommendations)
        watchlist = [r for r in sorted_recs if r.recommendation == RecommendationType.HOLD]
        if watchlist:
            sections.append(self._build_watchlist_section(watchlist))

        # Data Collection Status
        sections.append(self._build_status_section(collected_data))

        # Execution Metrics
        if execution_metrics:
            sections.append(self._build_metrics_section(execution_metrics))

        # Disclaimer
        sections.append(self._build_disclaimer())

        return "\n\n".join(sections)

    def _build_header(self, timestamp: datetime) -> str:
        """Build the report header."""
        date_str = timestamp.strftime("%B %d, %Y")
        time_str = timestamp.strftime("%H:%M:%S %Z")

        return f"""# Trading Recommendations - {date_str}

**Generated**: {timestamp.strftime('%Y-%m-%d')} at {time_str}
**Data Sources**: Yahoo Finance, FINVIZ, Investing.com, Pattern Analysis

---"""

    def _build_market_overview(self, collected_data: Dict[str, Any]) -> str:
        """Build market overview section."""
        lines = ["## Market Overview"]

        # Futures data if available
        futures_data = collected_data.get('futures', {})
        if not futures_data:
            # Try from yahoo futures
            yahoo_data = collected_data.get('yahoo', {})
            # Check for futures symbols
            for symbol in ['ES=F', 'NQ=F', 'YM=F']:
                if symbol in yahoo_data:
                    futures_data[symbol.replace('=F', '')] = yahoo_data[symbol]

        investing_data = collected_data.get('investing', {})
        if investing_data:
            futures_data.update(investing_data)

        if futures_data:
            lines.append("\n### Futures Snapshot")
            lines.append("| Contract | Price | Change |")
            lines.append("|----------|-------|--------|")

            for symbol, data in futures_data.items():
                if hasattr(data, 'current_price'):
                    price = data.current_price
                    change = getattr(data, 'change_percent', 0)
                    change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                    name = getattr(data, 'name', symbol)
                    lines.append(f"| {name} | ${price:,.2f} | {change_str} |")
                elif hasattr(data, 'last_price'):
                    price = data.last_price
                    change = getattr(data, 'change_percent', 0)
                    change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                    name = getattr(data, 'name', symbol)
                    lines.append(f"| {name} | ${price:,.2f} | {change_str} |")
        else:
            lines.append("\n*Futures data not available*")

        return "\n".join(lines)

    def _build_recommendation_section(
        self, title: str, recommendations: List[Recommendation]
    ) -> str:
        """Build a recommendation section."""
        lines = [f"## {title}"]

        for rec in recommendations:
            lines.append(self._format_recommendation(rec))

        return "\n".join(lines)

    def _format_recommendation(self, rec: Recommendation) -> str:
        """Format a single recommendation."""
        # Determine emoji based on recommendation type
        emoji_map = {
            RecommendationType.STRONG_BUY: "",
            RecommendationType.BUY: "",
            RecommendationType.HOLD: "",
            RecommendationType.SELL: "",
            RecommendationType.STRONG_SELL: "",
        }

        lines = [
            f"\n### {rec.recommendation.value}: {rec.symbol}",
            "",
            f"- **Current Price**: {rec.to_dict()['current_price']}",
            f"- **Target Price**: {rec.to_dict()['price_target']}",
            f"- **Stop Loss**: {rec.to_dict()['stop_loss']}",
            f"- **Confidence**: {rec.confidence_level} ({rec.confidence * 100:.0f}%)",
            "",
            f"**Rationale**: {rec.rationale}",
            "",
            "**Key Signals**:",
        ]

        for signal in rec.key_signals[:5]:
            lines.append(f"- {signal}")

        if rec.risks:
            lines.append("")
            lines.append("**Risks**:")
            for risk in rec.risks:
                lines.append(f"- {risk}")

        return "\n".join(lines)

    def _build_watchlist_section(self, recommendations: List[Recommendation]) -> str:
        """Build the watchlist section for HOLD recommendations."""
        lines = ["## Watchlist", "", "*Symbols to monitor but no immediate action recommended*", ""]

        lines.append("| Symbol | Price | Signals | Notes |")
        lines.append("|--------|-------|---------|-------|")

        for rec in recommendations:
            price = rec.to_dict()['current_price']
            signal_summary = f"B:{rec.signal_summary['bullish']} N:{rec.signal_summary['neutral']} S:{rec.signal_summary['bearish']}"
            note = rec.key_signals[0] if rec.key_signals else "Mixed signals"
            lines.append(f"| {rec.symbol} | {price} | {signal_summary} | {note} |")

        return "\n".join(lines)

    def _build_status_section(self, collected_data: Dict[str, Any]) -> str:
        """Build the data collection status section."""
        lines = ["## Data Collection Status", ""]

        sources = [
            ('Yahoo Finance', 'yahoo'),
            ('FINVIZ', 'finviz'),
            ('Investing.com', 'investing'),
            ('Pattern Analysis', 'patterns'),
        ]

        for name, key in sources:
            data = collected_data.get(key, {})
            if data:
                count = len(data)
                status = f"Success ({count} symbols)"
                lines.append(f"- **{name}**: {status}")
            else:
                lines.append(f"- **{name}**: Not available or failed")

        return "\n".join(lines)

    def _build_metrics_section(self, metrics: Dict[str, Any]) -> str:
        """Build execution metrics section."""
        lines = ["## Execution Metrics", ""]

        if 'start_time' in metrics:
            lines.append(f"- **Start Time**: {metrics['start_time']}")
        if 'end_time' in metrics:
            lines.append(f"- **End Time**: {metrics['end_time']}")
        if 'duration' in metrics:
            lines.append(f"- **Duration**: {metrics['duration']:.2f} seconds")
        if 'symbols_processed' in metrics:
            lines.append(f"- **Symbols Processed**: {metrics['symbols_processed']}")

        return "\n".join(lines)

    def _build_disclaimer(self) -> str:
        """Build the disclaimer section."""
        return """---

## Disclaimer

**IMPORTANT**: These recommendations are generated algorithmically for informational purposes only and do not constitute financial advice.

- Always conduct your own research and due diligence
- Consult with licensed financial advisors before trading
- Past performance does not guarantee future results
- Never invest more than you can afford to lose

The creators of this tool assume no liability for trading losses resulting from following these recommendations."""

    def _sort_recommendations(
        self, recommendations: Dict[str, Recommendation]
    ) -> List[Recommendation]:
        """Sort recommendations by type priority and confidence."""
        # Priority order: STRONG_BUY, BUY, SELL, STRONG_SELL, HOLD
        priority = {
            RecommendationType.STRONG_BUY: 0,
            RecommendationType.BUY: 1,
            RecommendationType.STRONG_SELL: 2,
            RecommendationType.SELL: 3,
            RecommendationType.HOLD: 4,
        }

        sorted_recs = sorted(
            recommendations.values(),
            key=lambda r: (priority.get(r.recommendation, 5), -r.confidence),
        )

        return sorted_recs
