# D.A.T.A. Setup Guide

This guide covers setting up the D.A.T.A. trading system for both local development and GitHub Actions deployment.

## Table of Contents

- [Local Development Setup](#local-development-setup)
- [GitHub Actions Setup](#github-actions-setup)
- [Configuration](#configuration)
- [Verification](#verification)

## Local Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- Virtual environment tool (venv, conda, etc.)

### Step 1: Clone and Install

```bash
# Clone the repository
git clone https://github.com/john-fizer/Agentic-Trader.git
cd Agentic-Trader

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install in development mode
pip install -e ".[dev]"
```

### Step 2: Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your actual credentials
nano .env  # or use your preferred editor
```

**Minimum required in .env:**
```bash
ALPACA_API_KEY=your_actual_key
ALPACA_API_SECRET=your_actual_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

### Step 3: Verify Installation

```bash
# Run tests to ensure everything is installed correctly
pytest

# Check code formatting
black --check src tests

# Lint code
ruff check src tests

# Type check (may have warnings initially)
mypy src
```

### Step 4: Run the System Locally

```bash
# Create logs directory
mkdir -p logs

# Run the system
python -m src.orchestrator.main
```

You should see output like:
```
2024-12-17 10:30:00 | INFO     | orchestrator | Initializing D.A.T.A. Trading System
2024-12-17 10:30:01 | INFO     | orchestrator | D.A.T.A. System initialized successfully
2024-12-17 10:30:01 | INFO     | orchestrator | Starting main trading loop
```

Press `Ctrl+C` to stop the system.

## GitHub Actions Setup

### Prerequisites

- GitHub account with access to the repository
- Alpaca API credentials (minimum)
- Repository with Actions enabled

### Step 1: Fork or Clone Repository

If you forked the repository, GitHub Actions will be available automatically.

### Step 2: Configure Secrets

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**

**Required Secrets:**
```
Name: ALPACA_API_KEY
Value: [Your Alpaca API Key]

Name: ALPACA_API_SECRET
Value: [Your Alpaca Secret Key]
```

**Optional Secrets** (add as needed):
```
BINANCE_API_KEY
BINANCE_API_SECRET
TIMESCALE_HOST
TIMESCALE_USER
TIMESCALE_PASSWORD
REDIS_HOST
REDIS_PASSWORD
```

### Step 3: Enable Workflows

1. Go to the **Actions** tab
2. If prompted, click **I understand my workflows, go ahead and enable them**
3. You should see three workflows:
   - CI
   - Run Trading System
   - Scheduled Trading

### Step 4: Test the Setup

1. Click on **Run Trading System** workflow
2. Click **Run workflow**
3. Set duration to 5 minutes
4. Click **Run workflow** button
5. Wait for completion and check logs

## Configuration

### Strategy Configuration

Edit `config/strategies.yml` to customize trading strategies:

```yaml
trend_following:
  enabled: true
  timeframes: ['1h', '4h', 'd']
  indicators:
    fast_ma: 20
    slow_ma: 50
    adx_threshold: 25

mean_reversion:
  enabled: true
  timeframes: ['1h', '4h']
  indicators:
    rsi_oversold: 30
    rsi_overbought: 70
```

### Risk Configuration

Edit `config/risk.yml` to adjust risk parameters:

```yaml
per_trade:
  max_risk_per_trade: 0.01  # 1% of equity
  min_reward_risk_ratio: 1.5

portfolio:
  max_portfolio_heat: 0.06  # 6% total risk
  max_positions: 20
  max_sector_concentration: 0.30
  max_single_name_exposure: 0.15

circuit_breakers:
  max_daily_drawdown: 0.05  # 5%
  max_consecutive_losses: 10
  max_trades_per_day: 100
```

### Data Sources Configuration

Edit `config/data_sources.yml` for data providers:

```yaml
primary_data_source: alpaca

sources:
  alpaca:
    enabled: true
    rate_limit: 200  # requests per minute
    
  polygon:
    enabled: false
    # api_key: set in environment
    
  binance:
    enabled: false
    # credentials in environment
```

## Verification

### Local Verification

```bash
# 1. Run all tests
pytest --cov=src

# 2. Check code quality
black src tests
ruff check src tests
mypy src

# 3. Run system for 1 minute
timeout 1m python -m src.orchestrator.main || true

# 4. Check logs
ls -l logs/
tail logs/*.log
```

### GitHub Actions Verification

1. **CI Workflow**: Should pass automatically on push
   - Check that all tests pass
   - Verify linting passes
   - Confirm build succeeds

2. **Manual Run**: Test with 5-minute duration
   - Check workflow completes successfully
   - Download and review logs artifact
   - Verify system initialized correctly

3. **Scheduled Run**: Only enable after thorough testing
   - Test manually first using workflow_dispatch
   - Monitor first scheduled run closely
   - Review logs for any issues

## Troubleshooting

### Common Issues

#### Import Errors
```bash
# Reinstall dependencies
pip install -e ".[dev]" --force-reinstall
```

#### Missing Configuration Files
```bash
# Verify config directory
ls -l config/
# Should see: strategies.yml, risk.yml, data_sources.yml
```

#### API Connection Issues
```bash
# Test API connection
python -c "
import os
from alpaca_trade_api import REST
api = REST(
    os.getenv('ALPACA_API_KEY'),
    os.getenv('ALPACA_API_SECRET'),
    os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
)
print('Account:', api.get_account())
"
```

#### Log Permission Issues
```bash
# Create logs directory with proper permissions
mkdir -p logs
chmod 755 logs
```

### Getting Help

If you encounter issues:

1. **Check Documentation**:
   - This SETUP.md file
   - [README.md](README.md)
   - [.github/workflows/README.md](.github/workflows/README.md)
   - [.github/QUICKSTART.md](.github/QUICKSTART.md)

2. **Review Logs**:
   - Local: `logs/` directory
   - GitHub Actions: Workflow artifacts

3. **Common Resources**:
   - [Alpaca API Docs](https://alpaca.markets/docs/)
   - [GitHub Actions Docs](https://docs.github.com/en/actions)
   - [Python Packaging](https://packaging.python.org/)

4. **Get Support**:
   - Open a GitHub Issue with:
     - Error message or unexpected behavior
     - Steps to reproduce
     - Log files (sanitize any secrets!)
     - Environment details (OS, Python version)

## Next Steps

After successful setup:

1. **Test Thoroughly**: Run multiple test cycles before live deployment
2. **Customize Strategies**: Adjust parameters in config files
3. **Monitor Performance**: Track system behavior and results
4. **Enable Scheduling**: Only after extensive testing
5. **Set Up Alerts**: Configure notifications for failures

## Security Best Practices

- ✅ Never commit .env files or secrets
- ✅ Use GitHub Secrets for sensitive data
- ✅ Rotate API keys regularly
- ✅ Start with paper trading
- ✅ Monitor API usage and rate limits
- ✅ Review logs for suspicious activity
- ✅ Keep dependencies updated

## Maintenance

### Regular Tasks

- **Daily**: Review trading logs and system health
- **Weekly**: Check for dependency updates
- **Monthly**: Review and optimize strategies
- **Quarterly**: Full system audit and testing

### Updates

```bash
# Update dependencies
pip install --upgrade -e ".[dev]"

# Run tests after updates
pytest --cov=src

# Update configuration if needed
git pull origin main
```

---

**Ready to Start?** Follow the [Quick Start Guide](.github/QUICKSTART.md) for a rapid deployment using GitHub Actions!
