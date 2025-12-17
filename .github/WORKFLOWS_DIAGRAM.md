# GitHub Actions Workflows Diagram

## Workflow Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                      GITHUB REPOSITORY                              │
│                   john-fizer/Agentic-Trader                         │
└────────────────────────────────────────────────────────────────────┘
                              │
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  CI Workflow │    │ Run Trading      │    │ Scheduled       │
│   (ci.yml)   │    │ System Workflow  │    │ Trading         │
│              │    │ (run-trading-    │    │ Workflow        │
│              │    │  system.yml)     │    │ (scheduled-     │
│              │    │                  │    │  trading.yml)   │
└──────────────┘    └──────────────────┘    └─────────────────┘
       │                     │                      │
       │                     │                      │
       ▼                     ▼                      ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   TRIGGERS   │    │    TRIGGERS      │    │   TRIGGERS      │
│              │    │                  │    │                 │
│ • Push       │    │ • Manual         │    │ • Cron          │
│ • Pull Req   │    │   (workflow_     │    │   (disabled)    │
│ • Manual     │    │   dispatch)      │    │ • Manual        │
└──────────────┘    └──────────────────┘    └─────────────────┘
       │                     │                      │
       │                     │                      │
       ▼                     ▼                      ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│     JOBS     │    │      JOBS        │    │     JOBS        │
│              │    │                  │    │                 │
│ • Test       │    │ • Setup Python   │    │ • Setup Python  │
│   Python     │    │ • Install deps   │    │ • Install deps  │
│   3.10-3.12  │    │ • Run D.A.T.A.   │    │ • Check         │
│              │    │   for N minutes  │    │   schedule      │
│ • Lint       │    │ • Upload logs    │    │ • Run D.A.T.A.  │
│   (black,    │    │                  │    │ • Upload logs   │
│    ruff)     │    │                  │    │   & data        │
│              │    │                  │    │                 │
│ • Type Check │    │                  │    │                 │
│   (mypy)     │    │                  │    │                 │
│              │    │                  │    │                 │
│ • Build      │    │                  │    │                 │
│   Package    │    │                  │    │                 │
└──────────────┘    └──────────────────┘    └─────────────────┘
       │                     │                      │
       │                     │                      │
       ▼                     ▼                      ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   OUTPUTS    │    │    OUTPUTS       │    │    OUTPUTS      │
│              │    │                  │    │                 │
│ • Test       │    │ • Trading logs   │    │ • Trading logs  │
│   Results    │    │   (artifacts)    │    │   (artifacts)   │
│              │    │                  │    │                 │
│ • Coverage   │    │ • Log summary    │    │ • Trading data  │
│   Report     │    │   in output      │    │   (artifacts)   │
│              │    │                  │    │                 │
│ • Build      │    │ • Exit status    │    │ • Notifications │
│   Artifacts  │    │                  │    │                 │
└──────────────┘    └──────────────────┘    └─────────────────┘
```

## Workflow Relationships

```
                     ┌─────────────────────┐
                     │   Code Changes      │
                     │   (Push/PR)         │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │   CI Workflow       │◄────── Automatic
                     │   Runs Tests        │
                     └──────────┬──────────┘
                                │
                                ▼
                         Tests Pass? ────┐
                                         │
                        ┌────────────────┘
                        │ Yes
                        ▼
             ┌─────────────────────┐
             │   Ready to Merge    │
             └──────────┬──────────┘
                        │
                        ▼
             ┌─────────────────────┐
             │   Merge to Main     │
             └──────────┬──────────┘
                        │
                        ▼
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌──────────────────┐          ┌──────────────────┐
│ Manual Testing   │          │ Schedule         │
│ (Run Trading     │          │ (When Enabled)   │
│  System)         │          │                  │
└────────┬─────────┘          └────────┬─────────┘
         │                              │
         │                              │
         ▼                              ▼
┌──────────────────┐          ┌──────────────────┐
│ Test 5-60 min    │          │ Run at Market    │
│ Review Logs      │          │ Open/Close       │
│ Iterate Config   │          │ Automatic        │
└────────┬─────────┘          └────────┬─────────┘
         │                              │
         └──────────┬───────────────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │ Production Trading  │
         │ Monitor & Maintain  │
         └─────────────────────┘
```

## Secret Flow

```
┌─────────────────────────────────────┐
│   Repository Secrets                │
│   (Settings → Secrets → Actions)    │
│                                     │
│   • ALPACA_API_KEY                  │
│   • ALPACA_API_SECRET               │
│   • BINANCE_API_KEY                 │
│   • BINANCE_API_SECRET              │
│   • Database credentials            │
│   • Redis credentials               │
└────────────────┬────────────────────┘
                 │
                 │ Injected as
                 │ environment variables
                 ▼
┌─────────────────────────────────────┐
│   Workflow Execution                │
│   (Secure runner environment)       │
└────────────────┬────────────────────┘
                 │
                 │ Used by
                 ▼
┌─────────────────────────────────────┐
│   D.A.T.A. Trading System           │
│   (src/orchestrator/main.py)        │
│                                     │
│   • Reads from os.environ           │
│   • Connects to brokers             │
│   • Executes trades                 │
└─────────────────────────────────────┘
```

## Data Flow in Manual/Scheduled Runs

```
┌─────────────────┐
│ Workflow Start  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Install Python  │
│ & Dependencies  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Load Config     │
│ from config/    │
│ • strategies.yml│
│ • risk.yml      │
│ • data_sources  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Initialize      │
│ D.A.T.A. System │
│ • Agents        │
│ • Event Bus     │
│ • Orchestrator  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Main Loop       │
│ (N minutes)     │
│                 │
│ Every cycle:    │
│ 1. Build MSO    │
│ 2. Strategies   │
│ 3. Risk check   │
│ 4. Execute      │
│ 5. Feedback     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Generate Logs   │
│ logs/           │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Upload Artifacts│
│ (GitHub)        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Workflow End    │
└─────────────────┘
```

## Matrix Testing (CI Workflow)

```
                    CI Workflow
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Python   │    │ Python   │    │ Python   │
  │  3.10    │    │  3.11    │    │  3.12    │
  └────┬─────┘    └────┬─────┘    └────┬─────┘
       │               │               │
       ▼               ▼               ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Install  │    │ Install  │    │ Install  │
  │ & Test   │    │ & Test   │    │ & Test   │
  └────┬─────┘    └────┬─────┘    └────┬─────┘
       │               │               │
       └───────────────┼───────────────┘
                       │
                       ▼
                  All Pass?
                       │
                       ▼
                   ✅ Success
```

## Deployment Strategy

```
Phase 1: Testing
├── Run CI on every commit
├── Manual runs with 5-10 min duration
├── Review logs
└── Fix any issues

Phase 2: Validation  
├── Longer manual runs (30-60 min)
├── Test different market conditions
├── Verify strategy behavior
└── Adjust configuration

Phase 3: Automation (Optional)
├── Enable scheduled workflow
├── Monitor first runs closely
├── Set up alerts
└── Regular review

Phase 4: Production
├── Continuous monitoring
├── Regular maintenance
├── Strategy optimization
└── Performance tracking
```

## Legend

```
┌──────────┐
│ Box      │  = Component/Process
└──────────┘

    │
    ▼         = Data/Control Flow

┌──────────┐
│ • Item   │  = List/Options
└──────────┘

────────────  = Connection/Relationship
```

## Notes

1. **CI Workflow**: Runs automatically, no setup required after merge
2. **Manual Workflow**: Requires API secrets to be configured first
3. **Scheduled Workflow**: Disabled by default for safety
4. All workflows use the same codebase and configuration files
5. Logs and artifacts are automatically cleaned up after retention period
6. Python version matrix ensures compatibility across versions

## Quick Reference

| Workflow | Trigger | Setup Required | Purpose |
|----------|---------|----------------|---------|
| CI | Auto (push/PR) | None | Testing |
| Run Trading System | Manual | Secrets | Testing/Demo |
| Scheduled Trading | Cron/Manual | Secrets + Enable | Production |

For detailed documentation, see:
- [Workflows README](workflows/README.md)
- [Quick Start Guide](QUICKSTART.md)
- [Setup Guide](../SETUP.md)
