"""
Trading Data Agent - Main Orchestrator

This is the entry point for the trading agent.
It coordinates data collection, analysis, and report generation.

Usage:
    python src/main.py [config_path]

Examples:
    python src/main.py
    python src/main.py config/config.yaml
"""

import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.utils.logger import setup_logging, ExecutionTimer
from src.scrapers.yahoo_finance import YahooFinanceScraper
from src.scrapers.finviz import FinvizScraper
from src.scrapers.investing_com import InvestingComScraper
from src.scrapers.stockcharts import ChartPatternDetector
from src.analysis.signal_aggregator import SignalAggregator
from src.analysis.recommendation_engine import RecommendationEngine
from src.output.markdown_generator import MarkdownGenerator


class TradingAgent:
    """Main orchestrator for the trading data agent."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the trading agent.

        Args:
            config_path: Path to configuration file (optional)
        """
        # Load configuration
        self.config = Config(config_path)

        # Setup logging
        setup_logging(
            log_dir=self.config.log_directory,
            log_level=self.config.log_level,
        )

        self.logger = logging.getLogger(self.__class__.__name__)

        # Initialize components
        self._init_scrapers()
        self._init_analysis()
        self._init_output()

    def _init_scrapers(self) -> None:
        """Initialize data scrapers based on configuration."""
        self.scrapers: Dict[str, Any] = {}

        # Yahoo Finance (always enabled - primary source)
        if self.config.is_source_enabled('yahoo_finance'):
            self.scrapers['yahoo'] = YahooFinanceScraper(
                self.config.get_source_config('yahoo_finance')
            )
            self.logger.info("Yahoo Finance scraper initialized")

        # FINVIZ
        if self.config.is_source_enabled('finviz'):
            self.scrapers['finviz'] = FinvizScraper(
                self.config.get_source_config('finviz')
            )
            self.logger.info("FINVIZ scraper initialized")

        # Investing.com
        if self.config.is_source_enabled('investing_com'):
            self.scrapers['investing'] = InvestingComScraper(
                self.config.get_source_config('investing_com')
            )
            self.logger.info("Investing.com scraper initialized")

        # Pattern Analysis
        if self.config.is_source_enabled('stockcharts'):
            self.scrapers['patterns'] = ChartPatternDetector(
                self.config.get_source_config('stockcharts')
            )
            self.logger.info("Pattern detector initialized")

    def _init_analysis(self) -> None:
        """Initialize analysis components."""
        signal_config = self.config.get('signal_weights', {})
        rec_config = self.config.get('recommendation', {})

        self.aggregator = SignalAggregator(signal_config)
        self.recommendation_engine = RecommendationEngine(rec_config)

        self.logger.info("Analysis components initialized")

    def _init_output(self) -> None:
        """Initialize output generator."""
        self.markdown_generator = MarkdownGenerator(
            str(self.config.output_directory)
        )
        self.logger.info("Markdown generator initialized")

    def run(self) -> bool:
        """
        Execute the full trading analysis pipeline.

        Returns:
            bool: True if successful (even with partial data), False on critical failure
        """
        start_time = datetime.now()

        self.logger.info("=" * 60)
        self.logger.info(f"Trading Agent started at {start_time}")
        self.logger.info("=" * 60)

        # Get watchlist
        stocks = self.config.watchlist_stocks
        futures = self.config.watchlist_futures

        if not stocks:
            self.logger.error("No stocks in watchlist. Exiting.")
            return False

        self.logger.info(f"Processing {len(stocks)} stocks: {', '.join(stocks)}")
        self.logger.info(f"Tracking {len(futures)} futures: {', '.join(futures)}")

        # Collect data from all sources
        with ExecutionTimer("Data collection", self.logger):
            collected_data = self._collect_data(stocks, futures)

        # Check if we have minimum required data
        if not collected_data.get('yahoo'):
            self.logger.error("Yahoo Finance data required but unavailable. Exiting.")
            return False

        # Aggregate signals
        with ExecutionTimer("Signal aggregation", self.logger):
            aggregated_signals = self.aggregator.aggregate(
                yahoo_data=collected_data.get('yahoo', {}),
                finviz_data=collected_data.get('finviz', {}),
                investing_data=collected_data.get('investing', {}),
                pattern_data=collected_data.get('patterns', {}),
                symbols=stocks,
            )

        # Generate recommendations
        with ExecutionTimer("Recommendation generation", self.logger):
            recommendations = self.recommendation_engine.generate_recommendations(
                aggregated_signals=aggregated_signals,
                price_data=collected_data.get('yahoo', {}),
            )

        # Build execution metrics
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        execution_metrics = {
            'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'duration': duration,
            'symbols_processed': len(stocks),
        }

        # Generate output report
        with ExecutionTimer("Report generation", self.logger):
            output_path = self.markdown_generator.generate_report(
                recommendations=recommendations,
                aggregated_signals=aggregated_signals,
                collected_data=collected_data,
                execution_metrics=execution_metrics,
            )

        # Summary
        self.logger.info("=" * 60)
        self.logger.info(f"Report generated: {output_path}")
        self.logger.info(f"Total execution time: {duration:.2f} seconds")
        self.logger.info("=" * 60)

        # Log recommendation summary
        self._log_recommendation_summary(recommendations)

        return True

    def _collect_data(
        self, stocks: list, futures: list
    ) -> Dict[str, Any]:
        """
        Collect data from all sources with graceful error handling.

        Each source is wrapped in try/except to ensure one failure
        doesn't stop the entire pipeline.
        """
        data: Dict[str, Any] = {}

        # Yahoo Finance (required)
        if 'yahoo' in self.scrapers:
            self.logger.info("Fetching Yahoo Finance data...")
            try:
                data['yahoo'] = self.scrapers['yahoo'].fetch_data(stocks)
                self.logger.info(
                    f"  Retrieved data for {len(data['yahoo'])} symbols"
                )

                # Also get futures data from Yahoo
                futures_symbols = [f"{f}=F" for f in futures]
                yahoo_futures = self.scrapers['yahoo'].fetch_futures_data(futures)
                if yahoo_futures:
                    data['futures'] = yahoo_futures
                    self.logger.info(
                        f"  Retrieved futures data for {len(yahoo_futures)} contracts"
                    )

            except Exception as e:
                self.logger.error(f"Yahoo Finance failed: {e}")
                data['yahoo'] = {}

        # FINVIZ (optional)
        if 'finviz' in self.scrapers:
            self.logger.info("Fetching FINVIZ data...")
            try:
                data['finviz'] = self.scrapers['finviz'].fetch_data(stocks)
                self.logger.info(
                    f"  Retrieved data for {len(data['finviz'])} symbols"
                )
            except Exception as e:
                self.logger.warning(f"FINVIZ failed (continuing without): {e}")
                data['finviz'] = {}

        # Investing.com (optional)
        if 'investing' in self.scrapers:
            self.logger.info("Fetching Investing.com futures data...")
            try:
                data['investing'] = self.scrapers['investing'].fetch_data(futures)
                self.logger.info(
                    f"  Retrieved data for {len(data['investing'])} contracts"
                )
            except Exception as e:
                self.logger.warning(
                    f"Investing.com failed (continuing without): {e}"
                )
                data['investing'] = {}

        # Pattern Analysis (optional)
        if 'patterns' in self.scrapers:
            self.logger.info("Analyzing chart patterns...")
            try:
                data['patterns'] = self.scrapers['patterns'].fetch_data(stocks)
                self.logger.info(
                    f"  Analyzed patterns for {len(data['patterns'])} symbols"
                )
            except Exception as e:
                self.logger.warning(
                    f"Pattern analysis failed (continuing without): {e}"
                )
                data['patterns'] = {}

        return data

    def _log_recommendation_summary(
        self, recommendations: Dict[str, Any]
    ) -> None:
        """Log a summary of recommendations."""
        from src.analysis.recommendation_engine import RecommendationType

        counts = {rec_type: 0 for rec_type in RecommendationType}

        for rec in recommendations.values():
            counts[rec.recommendation] += 1

        self.logger.info("Recommendation Summary:")
        for rec_type, count in counts.items():
            if count > 0:
                self.logger.info(f"  {rec_type.value}: {count}")


def main():
    """Entry point for the trading agent."""
    # Parse command line arguments
    config_path = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        # Run agent
        agent = TradingAgent(config_path)
        success = agent.run()
        sys.exit(0 if success else 1)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
