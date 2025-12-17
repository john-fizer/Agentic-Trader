# GitHub Actions Workflows

This directory contains GitHub Actions workflows for the D.A.T.A. (Domain-Aware Trading Agent) system.

## Available Workflows

### 1. CI Workflow (`ci.yml`)

**Purpose**: Continuous Integration - automated testing, linting, and building.

**Triggers**:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches
- Manual dispatch via GitHub Actions UI

**Jobs**:
- **Test**: Runs unit tests with coverage on Python 3.10, 3.11, and 3.12
- **Lint**: Checks code formatting (black), linting (ruff), and type checking (mypy)
- **Build**: Builds the Python package

**Status Badge**:
```markdown
[![CI](https://github.com/john-fizer/Agentic-Trader/actions/workflows/ci.yml/badge.svg)](https://github.com/john-fizer/Agentic-Trader/actions/workflows/ci.yml)
```

### 2. Run Trading System (`run-trading-system.yml`)

**Purpose**: Manually run the D.A.T.A. trading system for testing and validation.

**Triggers**:
- Manual dispatch only (via GitHub Actions UI)

**Parameters**:
- `duration`: How long to run the system (in minutes, default: 5)
- `log_level`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

**Requirements**:
Before running, configure the following repository secrets:
- `ALPACA_API_KEY` - Alpaca API key for equities trading
- `ALPACA_API_SECRET` - Alpaca API secret
- `BINANCE_API_KEY` - (Optional) Binance API key for crypto
- `BINANCE_API_SECRET` - (Optional) Binance API secret
- `TIMESCALE_HOST` - (Optional) TimescaleDB host
- `TIMESCALE_USER` - (Optional) TimescaleDB user
- `TIMESCALE_PASSWORD` - (Optional) TimescaleDB password
- `REDIS_HOST` - (Optional) Redis host
- `REDIS_PASSWORD` - (Optional) Redis password

**How to Run**:
1. Go to the "Actions" tab in GitHub
2. Select "Run Trading System" from the workflows list
3. Click "Run workflow"
4. Set desired duration and log level
5. Click "Run workflow" to start

**Outputs**:
- Trading logs are uploaded as artifacts (retained for 30 days)
- Log summary is displayed in the workflow output

### 3. Scheduled Trading (`scheduled-trading.yml`)

**Purpose**: Run the trading system on a schedule (e.g., at market open/close).

**Triggers**:
- **Scheduled** (currently disabled by default)
- Manual dispatch via GitHub Actions UI

**Default Schedule** (when enabled):
- Monday-Friday at 9:30 AM ET (market open)
- Monday-Friday at 4:00 PM ET (market close)

⚠️ **IMPORTANT**: This workflow is **disabled by default**. To enable scheduled runs:

1. Configure all required secrets (see Run Trading System section)
2. Edit `scheduled-trading.yml`
3. Uncomment the `schedule` section
4. Adjust cron times for your timezone and DST
5. Commit and push the changes

**Requirements**:
- Same secrets as "Run Trading System" workflow
- Proper market data access
- Sufficient GitHub Actions minutes

**Safety Features**:
- Configurable timeout (default: 120 minutes)
- Automatic log and data backup
- Failure notifications (customize in workflow)

**Outputs**:
- Trading logs (retained for 90 days)
- Trading data (retained for 90 days)
- Failure notifications

## Setting Up Secrets

To run the trading system, you need to configure repository secrets:

1. Go to your repository on GitHub
2. Click "Settings" → "Secrets and variables" → "Actions"
3. Click "New repository secret"
4. Add each required secret with its value

### Required Secrets (Minimum):
- `ALPACA_API_KEY`: Your Alpaca API key
- `ALPACA_API_SECRET`: Your Alpaca API secret

### Optional Secrets (for full functionality):
- `BINANCE_API_KEY`: For cryptocurrency trading
- `BINANCE_API_SECRET`: Binance secret
- `TIMESCALE_HOST`: For persistent data storage
- `TIMESCALE_USER`: Database user
- `TIMESCALE_PASSWORD`: Database password
- `REDIS_HOST`: For caching and messaging
- `REDIS_PASSWORD`: Redis password

## Best Practices

### Development Workflow
1. Make changes in a feature branch
2. CI workflow runs automatically on PR
3. Review test results and fix any failures
4. Merge to main/develop after approval

### Testing Changes
1. Use "Run Trading System" workflow with short duration (5-10 minutes)
2. Review logs to ensure system behaves correctly
3. Gradually increase duration for longer tests

### Production Deployment
1. Test thoroughly with manual runs first
2. Enable scheduled runs only after validation
3. Monitor logs regularly for issues
4. Set up notifications for failures

### Security Considerations
- **Never commit API keys or secrets to the repository**
- Use GitHub Secrets for all sensitive data
- Regularly rotate API keys
- Monitor API usage and rate limits
- Review workflow logs for suspicious activity

## Troubleshooting

### CI Workflow Fails
- Check Python version compatibility
- Verify all dependencies are in requirements.txt or pyproject.toml
- Review test output for specific failures

### Trading System Doesn't Start
- Verify all required secrets are configured
- Check that API credentials are valid
- Review configuration files in `config/` directory
- Check workflow logs for error messages

### Missing Logs
- Ensure `logs/` directory is created (workflow does this automatically)
- Check artifact upload didn't fail
- Verify log retention settings

### Scheduled Workflow Not Running
- Confirm schedule is uncommented in the workflow file
- Check cron syntax is correct
- Note: GitHub Actions scheduled workflows may have slight delays

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [D.A.T.A. System README](../../README.md)
- [Configuration Guide](../../config/)

## Support

For issues or questions:
1. Check existing GitHub Issues
2. Review workflow logs for error messages
3. Open a new issue with relevant details
