# D.A.T.A. - Domain-Aware Trading Agent

[![CI](https://github.com/john-fizer/Agentic-Trader/actions/workflows/ci.yml/badge.svg)](https://github.com/john-fizer/Agentic-Trader/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A multi-agent, domain-aware trading system designed to behave like a miniature hedge fund:
regime-aware, risk-first, multi-timeframe, multi-asset, and continuously learning.

## Overview

D.A.T.A. (Domain-Aware Trading Agent) is a sophisticated trading system composed of specialized sub-agents that work together to analyze markets, generate trade ideas, manage risk, execute orders, and learn from outcomes.

### Key Features

- **Regime-Aware Trading**: Automatically adapts strategies based on market regime (trending, mean-reverting, choppy, panic)
- **Multi-Timeframe Analysis**: Uses macro (D/W), meso (1H/4H), and micro (1-15M) timeframes for precision entries
- **Risk-First Architecture**: Portfolio heat limits, position sizing, drawdown controls, and circuit breakers
- **Multi-Asset Support**: Equities, options, futures, and crypto
- **Machine Learning Integration**: Feature engineering, direction classifiers, and continuous learning
- **Closed Feedback Loop**: Trade outcomes feed back into strategy and model improvements

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                              │
│  (Coordinates agents, enforces global rules, manages lifecycle)  │
└─────────────────────────────────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌───────────────┐
│  INITIALIZER  │───▶│    STRATEGY     │───▶│     RISK      │
│    AGENT      │    │     AGENTS      │    │    AGENT      │
│               │    │                 │    │               │
│ Builds MSO    │    │ Generate trade  │    │ Filter/size   │
│ Sets regime   │    │ ideas           │    │ trades        │
│ Key levels    │    │ Multi-strategy  │    │ Portfolio     │
└───────────────┘    └─────────────────┘    └───────────────┘
                                                    │
                     ┌──────────────────────────────┘
                     ▼
           ┌─────────────────┐    ┌───────────────┐
           │   EXECUTION     │───▶│   FEEDBACK    │
           │     AGENT       │    │    AGENT      │
           │                 │    │               │
           │ Route orders    │    │ Track PnL     │
           │ Manage fills    │    │ Update models │
           │ Track slippage  │    │ Learn & adapt │
           └─────────────────┘    └───────────────┘
```

### Core Components

- **Market State Object (MSO)**: Shared context containing regime, volatility, liquidity, session info, and per-instrument states
- **Orchestrator**: Coordinates the agent pipeline, enforces global constraints, manages kill switches
- **Initializer Agent**: Builds the MSO, determines which strategies are allowed
- **Strategy Agents**: Generate candidate trades based on market conditions
- **Risk Agent**: Evaluates trades, sizes positions, enforces portfolio limits
- **Execution Agent**: Routes orders to brokers, tracks execution quality
- **Feedback Agent**: Analyzes outcomes, triggers model retraining

## Installation

```bash
# Clone the repository
git clone https://github.com/john-fizer/Agentic-Trader.git
cd Agentic-Trader

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"
```

## Quick Start

```python
import asyncio
from src.orchestrator.main import DATASystem

async def main():
    system = DATASystem()
    await system.initialize()
    await system.run()

asyncio.run(main())
```

Or run from command line:

```bash
python -m src.orchestrator.main
```

## Configuration

Configuration files are in the `config/` directory:

- `strategies.yml` - Strategy parameters and settings
- `risk.yml` - Risk limits and portfolio constraints
- `data_sources.yml` - Data providers and storage configuration

### Environment Variables

```bash
# Broker APIs
ALPACA_API_KEY=your_key
ALPACA_API_SECRET=your_secret

# Crypto (optional)
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# Database (optional)
TIMESCALE_HOST=localhost
TIMESCALE_USER=postgres
TIMESCALE_PASSWORD=password

# Redis (optional)
REDIS_HOST=localhost
REDIS_PASSWORD=password
```

## Project Structure

```
Agentic-Trader/
├── config/
│   ├── strategies.yml      # Strategy configurations
│   ├── risk.yml            # Risk parameters
│   └── data_sources.yml    # Data source configs
├── data/
│   ├── raw/               # Raw market data
│   └── processed/         # Processed features
├── src/
│   ├── core/              # Core data models
│   │   ├── market_state.py  # MSO definition
│   │   ├── events.py        # Event system
│   │   └── trade.py         # Trade models
│   ├── orchestrator/      # Main orchestrator
│   ├── agents/
│   │   ├── initializer/   # Builds MSO
│   │   ├── strategy/      # Trade generation
│   │   ├── risk/          # Risk management
│   │   ├── execution/     # Order execution
│   │   └── feedback/      # Learning loop
│   ├── ml/
│   │   ├── features/      # Feature engineering
│   │   ├── models/        # ML models
│   │   └── training/      # Training pipelines
│   └── infra/
│       ├── db/            # Database
│       ├── messaging/     # Event messaging
│       └── logging/       # Logging config
├── tests/
│   ├── unit/
│   └── integration/
├── notebooks/             # Research notebooks
└── docs/                  # Documentation
```

## Built-in Strategies

### Trend Following
- Uses moving average crossovers to identify trends
- Confirms with ADX for trend strength
- Enters on pullbacks within the trend
- ATR-based stops and targets

### Mean Reversion
- Identifies oversold/overbought using RSI and Bollinger Bands
- Enters at price extremes
- Targets return to mean
- Tight stops for failed reversals

## Risk Management

### Per-Trade Limits
- Max risk per trade: 1% of equity (configurable)
- Minimum reward/risk ratio: 1.5x

### Portfolio Limits
- Max portfolio heat: 6% (sum of all open risk)
- Max positions: 20
- Max sector concentration: 30%
- Max single-name exposure: 15%

### Circuit Breakers
- Kill switch on 5% daily drawdown
- Auto-pause after 10 consecutive losses
- Max 100 trades per day

## GitHub Actions Workflows

This repository includes automated workflows for CI/CD and running the trading system:

### Continuous Integration (CI)
Automatically runs on every push and pull request:
- Runs tests across Python 3.10, 3.11, and 3.12
- Checks code formatting with Black
- Lints code with Ruff
- Type checks with MyPy
- Builds the package

### Run Trading System (Manual)
Manually trigger the trading system via GitHub Actions:
1. Go to the "Actions" tab
2. Select "Run Trading System"
3. Click "Run workflow"
4. Configure duration and log level
5. View logs in workflow artifacts

**Required Secrets**: Configure in repository settings:
- `ALPACA_API_KEY` and `ALPACA_API_SECRET` (required)
- Optional: `BINANCE_API_KEY`, `BINANCE_API_SECRET`, database credentials

### Scheduled Trading (Optional)
Run the system automatically on a schedule (disabled by default):
- Edit `.github/workflows/scheduled-trading.yml`
- Uncomment the schedule section
- Configure for your timezone and trading hours

See [.github/workflows/README.md](.github/workflows/README.md) for detailed documentation.

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src

# Format code
black src tests
ruff check src tests

# Type checking
mypy src
```

## Roadmap

- [ ] Real-time data integration
- [ ] Options strategies (spreads, iron condors)
- [ ] Futures roll management
- [ ] Advanced ML models (transformers, RL)
- [ ] Web dashboard
- [ ] Backtesting framework integration
- [ ] Multi-account support

## Disclaimer

This software is for educational and research purposes only. Do not use this system for live trading without proper testing, risk management, and understanding of the risks involved. The authors are not responsible for any financial losses incurred through use of this software.

## License

MIT License - see LICENSE file for details.
