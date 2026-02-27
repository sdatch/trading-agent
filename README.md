# Trading Data Agent

Automated trading data collection and analysis agent that generates daily stock and futures recommendations.

## Features

- **Multi-Source Data Collection**: Yahoo Finance, FINVIZ, Investing.com, and local pattern analysis
- **Technical Analysis**: RSI, MACD, SMA crossovers, chart patterns
- **Signal Aggregation**: Weighted combination of signals from all sources
- **Automated Recommendations**: BUY/SELL/HOLD with confidence levels and price targets
- **Daily Reports**: Date-stamped markdown files with full analysis

## Quick Start

### 1. Setup

```powershell
# Navigate to project directory
cd C:\Users\ghubl\projects\trading-agent

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure

Edit `config/config.yaml` to customize:
- Stock watchlist
- Futures contracts to track
- Data source settings
- Signal weights

### 3. Run

```powershell
# Run manually
python src/main.py

# Or use the batch file
.\run_agent.bat
```

### 4. Schedule Daily Execution

Run PowerShell as Administrator:

```powershell
.\setup_scheduler.ps1
```

This creates a Windows Task Scheduler job to run at 7:00 AM on weekdays.

## Output

Reports are generated in the `output/` directory:
- `trading-recommendations-2026-02-01.md`
- `trading-recommendations-2026-02-02.md`
- etc.

Each report contains:
- Market overview with futures snapshot
- High confidence recommendations
- Medium confidence recommendations
- Watchlist items
- Data collection status
- Execution metrics

## Project Structure

```
trading-agent/
├── src/
│   ├── main.py                 # Entry point
│   ├── config.py               # Configuration loader
│   ├── scrapers/               # Data source scrapers
│   │   ├── yahoo_finance.py
│   │   ├── finviz.py
│   │   ├── investing_com.py
│   │   └── stockcharts.py
│   ├── analysis/               # Signal processing
│   │   ├── signal_aggregator.py
│   │   └── recommendation_engine.py
│   ├── output/                 # Report generation
│   │   └── markdown_generator.py
│   └── utils/                  # Utilities
│       └── logger.py
├── config/
│   └── config.yaml             # Configuration
├── output/                     # Generated reports
├── logs/                       # Execution logs
├── requirements.txt
├── run_agent.bat
├── setup_scheduler.ps1
└── README.md
```

## Configuration

### Watchlist

```yaml
watchlist:
  stocks:
    - AAPL
    - MSFT
    - GOOGL
  futures:
    - ES
    - NQ
    - YM
```

### Signal Weights

Adjust how much each source and signal type contributes:

```yaml
signal_weights:
  source_weights:
    "Yahoo Finance": 1.0
    "FINVIZ": 0.8
    "Investing.com": 0.6
    "StockCharts / Pattern Analysis": 0.7
```

### Recommendation Thresholds

```yaml
recommendation:
  strong_threshold: 0.6    # Score for STRONG BUY/SELL
  moderate_threshold: 0.3  # Score for BUY/SELL
  min_confidence: 0.5      # Minimum confidence for action
  high_confidence: 0.7     # High confidence threshold
```

## Data Sources

| Source | Data Provided | Reliability |
|--------|--------------|-------------|
| Yahoo Finance | Price, volume, technicals | High (primary) |
| FINVIZ | Fundamentals, insider activity | Medium |
| Investing.com | Futures data | Low (Cloudflare issues) |
| Pattern Analysis | Chart patterns, support/resistance | Medium |

## Troubleshooting

### FINVIZ not returning data
- FINVIZ may rate-limit aggressive scraping
- Increase `rate_limit_seconds` in config

### Investing.com failing
- Cloudflare protection is aggressive
- The agent falls back to Yahoo Finance futures data

### First run downloads Chromium
- `requests-html` needs Chromium for JavaScript rendering
- This is a one-time ~150MB download

## Logs

Logs are stored in `logs/` with daily rotation:
- `trading-agent-2026-02-01.log`

## Disclaimer

**IMPORTANT**: This tool provides algorithmic analysis for informational purposes only. It does not constitute financial advice.

- Always conduct your own research
- Consult with licensed financial advisors
- Past performance does not guarantee future results
- Never invest more than you can afford to lose

The creators assume no liability for trading losses.

## License

For personal use only.
