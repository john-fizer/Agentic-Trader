# How to Run the D.A.T.A. Trading System

This guide shows you how to run the D.A.T.A. (Domain-Aware Trading Agent) trading system using GitHub Actions.

## 🚀 Quick Start (5 Minutes)

### Step 1: Get API Credentials (2 minutes)

1. Sign up for a free Alpaca account: https://alpaca.markets
2. Navigate to "Paper Trading" section
3. Generate API keys (they're free for paper trading)
4. Copy your API Key and Secret Key

### Step 2: Add Secrets to GitHub (2 minutes)

1. Go to your repository on GitHub
2. Click **Settings** (top navigation)
3. Click **Secrets and variables** → **Actions** (left sidebar)
4. Click **New repository secret** (green button)
5. Add two secrets:
   - Name: `ALPACA_API_KEY`, Value: (paste your API key)
   - Name: `ALPACA_API_SECRET`, Value: (paste your secret key)

### Step 3: Run the System (1 minute)

1. Click the **Actions** tab (top navigation)
2. Click **Run Trading System** (left sidebar)
3. Click **Run workflow** (right side, green button)
4. Keep defaults: Duration: 5, Log level: INFO
5. Click **Run workflow** (in the dropdown)
6. Watch it run! (about 5 minutes)

### Step 4: Check Results

1. Wait for the workflow to complete (green checkmark)
2. Click on the completed workflow run
3. Scroll to bottom → Click **trading-logs-[number]** under Artifacts
4. Download and unzip to view logs

## 🎯 What to Expect

Your first run should show:

```
✅ D.A.T.A. System initialized successfully
✅ Starting main trading loop
✅ Cycle complete: candidates=X, approved=Y, orders=Z
```

This means the system is working! The actual numbers depend on market conditions.

## 📊 Understanding the Output

### System Initialization
- **Initializer Agent**: Sets up market state
- **Strategy Manager**: Loads trading strategies
- **Risk Agent**: Enforces safety limits
- **Execution Agent**: Routes orders to brokers
- **Feedback Agent**: Tracks performance

### Trading Cycle
Each cycle (about 1 minute):
1. Analyzes current market conditions
2. Generates trade candidates from strategies
3. Applies risk filters
4. Executes approved trades
5. Logs results

### Log Files
- `data_YYYY-MM-DD.log`: Full system logs
- Contains INFO level messages by default
- Use DEBUG level for more detail

## 🎛️ Advanced Usage

### Longer Runs

After your first successful 5-minute run:

1. Go to Actions → Run Trading System
2. Set Duration to 30 (or 60 for 1 hour)
3. Run and monitor

### Debug Mode

To see detailed information:

1. Set Log level to DEBUG
2. Duration to 10-15 minutes
3. Review logs for detailed agent interactions

### Configuration Changes

Edit files in the `config/` directory:

**config/strategies.yml** - Strategy parameters:
```yaml
trend_following:
  enabled: true
  fast_ma: 20
  slow_ma: 50
```

**config/risk.yml** - Risk limits:
```yaml
per_trade:
  max_risk_per_trade: 0.01  # 1% per trade
portfolio:
  max_portfolio_heat: 0.06  # 6% total risk
```

Commit changes to apply them.

## 🔄 Automated Runs (Optional)

### Schedule Regular Trading

⚠️ **Only enable after thorough testing!**

1. Edit `.github/workflows/scheduled-trading.yml`
2. Find this section:
   ```yaml
   # schedule:
   #   - cron: '30 14 * * 1-5'  # 9:30 AM ET
   ```
3. Remove the `#` to uncomment
4. Adjust times for your timezone
5. Commit and push

The system will now run automatically at the scheduled times.

## 📈 Monitoring

### Check Workflow History

1. Go to Actions tab
2. See all recent runs
3. Green = successful, Red = failed
4. Click any run for details

### Download Logs

Logs are kept for 30 days (90 for scheduled runs):

1. Go to completed workflow
2. Scroll to Artifacts section
3. Download logs
4. Review for insights or issues

### Performance Tracking

The system logs:
- Trades generated
- Trades approved
- Orders placed
- Execution quality
- PnL tracking

## 🛠️ Troubleshooting

### "Workflow not found"

**Solution**: Merge this PR first, then workflows will appear.

### "Invalid credentials"

**Solutions**:
- Verify secrets are set in Settings → Secrets
- Check API keys are correct in Alpaca dashboard
- Ensure keys are for paper trading account

### "No trade candidates"

**This is normal!** The system is conservative and only trades when:
- Market conditions are favorable
- Strategy signals are present
- Risk limits allow it

### "Import errors"

**Solution**: Dependencies may have failed to install. Check the "Install dependencies" step in the workflow logs.

### "Timeout"

If the workflow times out:
- Reduce duration
- Check if system is stuck in logs
- Verify market data access is working

## 📚 More Resources

- **Quick Start**: `.github/QUICKSTART.md`
- **Full Setup Guide**: `SETUP.md`
- **Workflow Details**: `.github/workflows/README.md`
- **Architecture**: `.github/WORKFLOWS_DIAGRAM.md`
- **Main README**: `README.md`

## ⚠️ Important Safety Notes

1. **Start with Paper Trading**: Always use Alpaca's paper trading first
2. **Small Positions**: Configure conservative position sizes
3. **Monitor Actively**: Watch the first several runs
4. **Understand Risks**: Read the disclaimer in README.md
5. **Test Thoroughly**: Don't rush to live trading

## 🎓 Learning Path

### Week 1: Testing
- [ ] First 5-minute run
- [ ] 30-minute run
- [ ] Review all logs
- [ ] Understand output

### Week 2: Configuration
- [ ] Adjust strategy parameters
- [ ] Test different settings
- [ ] Monitor behavior changes
- [ ] Document findings

### Week 3: Extended Testing
- [ ] Multiple 1-hour runs
- [ ] Different market conditions
- [ ] Risk limit testing
- [ ] Performance analysis

### Week 4+: Production Ready
- [ ] Decide on live vs. paper
- [ ] Enable scheduling (if desired)
- [ ] Set up monitoring
- [ ] Regular reviews

## 🤝 Getting Help

### Documentation First
1. Check the documentation files listed above
2. Review workflow logs for error messages
3. Look for similar issues in GitHub Issues

### Still Stuck?
1. Open a GitHub Issue
2. Include:
   - What you tried to do
   - What happened instead
   - Relevant log excerpts (remove any secrets!)
   - Steps to reproduce

## ✅ Success Checklist

Before considering yourself "ready":

- [ ] Successfully run 5-minute test
- [ ] Downloaded and reviewed logs
- [ ] Understood system output
- [ ] Customized configuration
- [ ] Tested with different parameters
- [ ] Read all documentation
- [ ] Comfortable with the system behavior

Once complete, you're ready to use D.A.T.A. effectively!

## 🎉 You're All Set!

You now have:
- ✅ A fully functional trading system
- ✅ Automated CI/CD pipeline
- ✅ Comprehensive documentation
- ✅ Safe testing environment
- ✅ Monitoring and logging

Start with a 5-minute test run and build from there. Happy trading! 📈

---

**Remember**: This is a sophisticated system. Take your time to understand it. Start small, test thoroughly, and scale gradually.

**Questions?** Check the documentation or open an issue!
