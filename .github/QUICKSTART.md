# Quick Start Guide: Running D.A.T.A. with GitHub Actions

This guide will help you run the D.A.T.A. trading system using GitHub Actions in just a few minutes.

## Prerequisites

- GitHub account with access to this repository
- Alpaca API credentials (free tier available at [alpaca.markets](https://alpaca.markets))
- Basic understanding of GitHub Actions

## Step 1: Configure API Credentials

1. **Get Alpaca API Keys**:
   - Sign up at [alpaca.markets](https://alpaca.markets)
   - Go to Paper Trading API keys (for testing)
   - Copy your API Key and Secret Key

2. **Add Secrets to GitHub**:
   - Go to your repository on GitHub
   - Click **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**
   - Add the following secrets:
     - Name: `ALPACA_API_KEY`, Value: (your Alpaca API key)
     - Name: `ALPACA_API_SECRET`, Value: (your Alpaca secret key)

## Step 2: Run the Trading System

1. **Navigate to Actions**:
   - Click the **Actions** tab at the top of the repository

2. **Select the Workflow**:
   - In the left sidebar, click **Run Trading System**

3. **Run the Workflow**:
   - Click the **Run workflow** button (right side)
   - Configure options:
     - **Duration**: Set to 5 minutes for first test
     - **Log level**: Keep as INFO
   - Click **Run workflow** (green button)

4. **Monitor Progress**:
   - The workflow will appear in the list below
   - Click on it to see real-time progress
   - Wait for it to complete (about 5 minutes)

## Step 3: Review Results

1. **Check Workflow Status**:
   - ✅ Green checkmark = successful run
   - ❌ Red X = error occurred

2. **View Logs**:
   - Click on the workflow run
   - Click on the job "Run D.A.T.A. Trading System"
   - Expand steps to see detailed logs
   - Check the "Display log summary" step for highlights

3. **Download Logs**:
   - Scroll to the bottom of the workflow page
   - Under "Artifacts", click on `trading-logs-[number]`
   - Download and extract to view full logs

## What to Expect

On your first run, the system will:
1. ✅ Initialize all agents (Initializer, Strategy, Risk, Execution, Feedback)
2. ✅ Create a Market State Object (MSO)
3. ✅ Analyze market conditions
4. ✅ Generate trade candidates
5. ✅ Apply risk filters
6. ⚠️ May not execute actual trades (depends on market conditions)

Example successful output:
```
D.A.T.A. System initialized successfully
Starting main trading loop
Cycle complete: candidates=3, approved=1, orders=1
```

## Troubleshooting

### Workflow Fails Immediately
- **Cause**: Missing or invalid API credentials
- **Fix**: Double-check secrets are correctly set in repository settings

### No Trade Candidates Generated
- **Cause**: Market conditions don't meet strategy criteria
- **Fix**: This is normal! The system is conservative by design

### Import Errors
- **Cause**: Dependency installation failed
- **Fix**: Check CI workflow passes, review dependency versions

### Timeout
- **Cause**: Duration too short or system stuck
- **Fix**: Increase duration or check logs for errors

## Next Steps

### Test Longer Runs
Once your 5-minute test succeeds:
1. Run again with 30-60 minute duration
2. Review how the system behaves over time
3. Check how it handles different market conditions

### Enable Scheduled Runs
To run automatically at market open/close:
1. Review `.github/workflows/scheduled-trading.yml`
2. Uncomment the schedule section
3. Adjust times for your timezone
4. Commit and push changes
5. Monitor first few scheduled runs carefully

### Configure Additional Features
- Add database credentials for persistent storage
- Add crypto exchange keys for multi-asset trading
- Customize strategy parameters in `config/strategies.yml`
- Adjust risk limits in `config/risk.yml`

## Safety Reminders

⚠️ **IMPORTANT SAFETY NOTES**:

1. **Start with Paper Trading**: Always use Alpaca's paper trading API first
2. **Monitor Actively**: Watch the first several runs closely
3. **Small Positions**: Configure small position sizes initially
4. **Review Regularly**: Check logs after each run
5. **Understand Risks**: Read the disclaimer in README.md

## Getting Help

If you encounter issues:

1. **Check Documentation**:
   - [Main README](../README.md)
   - [Workflows README](workflows/README.md)
   - [Configuration Files](../config/)

2. **Review Logs**:
   - Download workflow artifacts
   - Check for error messages
   - Look for warnings or anomalies

3. **Common Issues**:
   - API rate limits: Reduce frequency or duration
   - Connection timeouts: Check network/API status
   - Invalid credentials: Regenerate API keys

4. **Get Support**:
   - Open a GitHub Issue with logs attached
   - Include workflow run number
   - Describe what you expected vs. what happened

## Advanced Usage

### Multiple Strategies
Edit `config/strategies.yml` to enable/disable strategies:
```yaml
trend_following:
  enabled: true
mean_reversion:
  enabled: true
```

### Custom Risk Limits
Edit `config/risk.yml`:
```yaml
portfolio:
  max_portfolio_heat: 0.06  # 6% max risk
  max_positions: 20
```

### Integration with External Systems
- Use workflow artifacts for downstream processing
- Set up notifications on completion/failure
- Export data to external databases

## Success Checklist

- [x] Alpaca API credentials configured as secrets
- [x] First 5-minute test run completed successfully
- [x] Logs downloaded and reviewed
- [x] System initialized without errors
- [ ] 30-minute test run completed
- [ ] Configuration customized for your needs
- [ ] Scheduled runs tested (if desired)
- [ ] Monitoring and alerting set up

Congratulations! You're now running D.A.T.A. on GitHub Actions! 🎉
