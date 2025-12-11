"""
Feedback Agent - Closes the learning loop.

The Feedback Agent is responsible for:
- Logging and evaluating trade outcomes (PnL, MFE/MAE, holding time, slippage)
- Computing strategy-level metrics (win rate, Sharpe, drawdowns)
- Analyzing regime-conditioned performance
- Triggering model retraining when thresholds are met
- Maintaining history of model versions and configurations
"""

from datetime import datetime, timedelta
from typing import Any, Optional
import json

from pydantic import BaseModel, Field
from loguru import logger

from src.agents.base import AgentConfig, BaseAgent
from src.core.events import Event, EventBus, EventType
from src.core.market_state import MarketStateObject, Regime
from src.core.trade import CandidateTrade, Order, OrderStatus, Position


class TradeRecord(BaseModel):
    """Complete record of a trade for analysis."""

    id: str
    timestamp: datetime
    symbol: str
    side: str
    strategy_name: str

    # Entry
    entry_price: float
    entry_time: datetime
    entry_features: dict[str, float] = Field(default_factory=dict)

    # Exit
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None

    # Market context
    regime: str
    volatility: str
    session: str

    # Performance
    pnl: float = 0.0
    pnl_percent: float = 0.0
    mfe: float = 0.0  # Maximum Favorable Excursion
    mae: float = 0.0  # Maximum Adverse Excursion
    holding_time_minutes: float = 0.0

    # Execution quality
    slippage: float = 0.0
    commission: float = 0.0

    # Signals
    signal_strength: float = 0.0
    predicted_direction: Optional[str] = None
    actual_direction: Optional[str] = None


class StrategyStats(BaseModel):
    """Statistics for a single strategy."""

    name: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0

    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    peak_equity: float = 0.0

    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None

    avg_holding_time_minutes: float = 0.0
    avg_mfe: float = 0.0
    avg_mae: float = 0.0

    # Regime breakdown
    stats_by_regime: dict[str, dict[str, float]] = Field(default_factory=dict)

    # Recent performance
    last_10_trades_pnl: float = 0.0
    last_10_win_rate: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0

    last_updated: datetime = Field(default_factory=datetime.utcnow)


class FeedbackAgentConfig(AgentConfig):
    """Configuration for the Feedback Agent."""

    name: str = "feedback"

    # Storage
    trade_log_path: str = "data/trade_log.jsonl"
    stats_path: str = "data/strategy_stats.json"

    # Retraining triggers
    min_trades_for_retrain: int = 100
    retrain_on_drawdown_percent: float = 10.0
    retrain_interval_days: int = 7

    # Performance thresholds
    strategy_pause_drawdown: float = 15.0
    strategy_pause_loss_streak: int = 10

    # Metrics calculation
    rolling_window_days: int = 30
    risk_free_rate: float = 0.05  # Annual risk-free rate for Sharpe


class FeedbackAgent(BaseAgent):
    """
    The Feedback Agent analyzes trade outcomes and triggers improvements.

    It maintains a complete history of trades and computes performance
    metrics to guide strategy adjustments and model retraining.
    """

    def __init__(
        self,
        config: FeedbackAgentConfig,
        event_bus: EventBus,
    ) -> None:
        super().__init__(config, event_bus)
        self.config: FeedbackAgentConfig = config

        # Trade history
        self._trade_history: list[TradeRecord] = []

        # Strategy statistics
        self._strategy_stats: dict[str, StrategyStats] = {}

        # Pending trades (awaiting exit)
        self._pending_trades: dict[str, TradeRecord] = {}

        # Model versioning
        self._model_versions: dict[str, str] = {}
        self._last_retrain_time: Optional[datetime] = None

    async def initialize(self) -> None:
        """Initialize the Feedback Agent."""
        self.logger.info("Initializing Feedback Agent")

        # Load existing trade history and stats
        await self._load_history()

        # Subscribe to relevant events
        self.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        self.subscribe(EventType.POSITION_CLOSED, self._on_position_closed)

        self.logger.info(
            f"Feedback Agent ready with {len(self._trade_history)} historical trades"
        )

    async def shutdown(self) -> None:
        """Shutdown the Feedback Agent."""
        self.logger.info("Shutting down Feedback Agent")

        # Save state
        await self._save_history()

    async def process(
        self, mso: MarketStateObject, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Process trade outcomes and update statistics.

        Args:
            mso: Current Market State Object
            candidate_trades: Trades that were proposed
            approved_trades: Trades that were approved by risk
            orders: Orders that were submitted

        Returns:
            Feedback summary including any recommendations
        """
        candidate_trades: list[CandidateTrade] = kwargs.get("candidate_trades", [])
        approved_trades: list[CandidateTrade] = kwargs.get("approved_trades", [])
        orders: list[Order] = kwargs.get("orders", [])

        feedback = {
            "timestamp": datetime.utcnow(),
            "trades_proposed": len(candidate_trades),
            "trades_approved": len(approved_trades),
            "orders_submitted": len(orders),
            "recommendations": [],
        }

        # Record new trades
        for order in orders:
            if order.status == OrderStatus.FILLED:
                trade = self._find_candidate_trade(order.candidate_trade_id, candidate_trades)
                if trade:
                    record = self._create_trade_record(trade, order, mso)
                    self._pending_trades[record.id] = record

        # Update statistics for closed trades
        closed_trades = kwargs.get("closed_trades", [])
        for closed in closed_trades:
            self._process_closed_trade(closed)

        # Check for retraining triggers
        retrain_needed = self._check_retrain_triggers()
        if retrain_needed:
            feedback["recommendations"].append({
                "type": "retrain",
                "reason": retrain_needed,
            })

        # Check strategy health
        for name, stats in self._strategy_stats.items():
            if stats.current_drawdown >= self.config.strategy_pause_drawdown:
                feedback["recommendations"].append({
                    "type": "pause_strategy",
                    "strategy": name,
                    "reason": f"Drawdown {stats.current_drawdown:.1f}%",
                })

            if stats.consecutive_losses >= self.config.strategy_pause_loss_streak:
                feedback["recommendations"].append({
                    "type": "pause_strategy",
                    "strategy": name,
                    "reason": f"Loss streak: {stats.consecutive_losses}",
                })

        return feedback

    def _find_candidate_trade(
        self, trade_id: Optional[str], trades: list[CandidateTrade]
    ) -> Optional[CandidateTrade]:
        """Find candidate trade by ID."""
        if not trade_id:
            return None
        for trade in trades:
            if trade.id == trade_id:
                return trade
        return None

    def _create_trade_record(
        self,
        trade: CandidateTrade,
        order: Order,
        mso: MarketStateObject,
    ) -> TradeRecord:
        """Create a trade record from trade and order data."""
        return TradeRecord(
            id=order.id,
            timestamp=datetime.utcnow(),
            symbol=trade.symbol,
            side=trade.side.value,
            strategy_name=trade.strategy_name,
            entry_price=order.average_fill_price or trade.entry_price or 0,
            entry_time=order.filled_at or datetime.utcnow(),
            entry_features=trade.features,
            regime=mso.regime.value,
            volatility=mso.volatility.value,
            session=mso.session.value,
            slippage=order.slippage or 0,
            commission=order.commission,
            signal_strength=trade.signal_strength,
        )

    def _process_closed_trade(self, closed: dict) -> None:
        """Process a closed trade and update statistics."""
        trade_id = closed.get("trade_id")

        if trade_id not in self._pending_trades:
            return

        record = self._pending_trades.pop(trade_id)

        # Update record with exit data
        record.exit_price = closed.get("exit_price", 0)
        record.exit_time = closed.get("exit_time", datetime.utcnow())
        record.exit_reason = closed.get("exit_reason")

        # Calculate performance metrics
        entry = record.entry_price
        exit_price = record.exit_price

        if record.side == "buy":
            record.pnl = (exit_price - entry) * closed.get("quantity", 1)
            record.pnl_percent = ((exit_price - entry) / entry) * 100
        else:
            record.pnl = (entry - exit_price) * closed.get("quantity", 1)
            record.pnl_percent = ((entry - exit_price) / entry) * 100

        # MFE/MAE
        record.mfe = closed.get("mfe", 0)
        record.mae = closed.get("mae", 0)

        # Holding time
        if record.exit_time and record.entry_time:
            delta = record.exit_time - record.entry_time
            record.holding_time_minutes = delta.total_seconds() / 60

        # Add to history
        self._trade_history.append(record)

        # Update strategy stats
        self._update_strategy_stats(record)

        self.logger.info(
            f"Trade closed: {record.symbol} {record.side} "
            f"PnL=${record.pnl:.2f} ({record.pnl_percent:.2f}%)"
        )

    def _update_strategy_stats(self, record: TradeRecord) -> None:
        """Update statistics for a strategy after a trade."""
        name = record.strategy_name

        if name not in self._strategy_stats:
            self._strategy_stats[name] = StrategyStats(name=name)

        stats = self._strategy_stats[name]

        # Update counts
        stats.total_trades += 1
        if record.pnl > 0:
            stats.winning_trades += 1
            stats.gross_profit += record.pnl
            stats.consecutive_wins += 1
            stats.consecutive_losses = 0
        else:
            stats.losing_trades += 1
            stats.gross_loss += abs(record.pnl)
            stats.consecutive_losses += 1
            stats.consecutive_wins = 0

        stats.total_pnl += record.pnl

        # Update ratios
        if stats.total_trades > 0:
            stats.win_rate = stats.winning_trades / stats.total_trades

        if stats.gross_loss > 0:
            stats.profit_factor = stats.gross_profit / stats.gross_loss

        if stats.winning_trades > 0:
            stats.avg_win = stats.gross_profit / stats.winning_trades

        if stats.losing_trades > 0:
            stats.avg_loss = stats.gross_loss / stats.losing_trades

        # Expectancy
        stats.expectancy = (
            stats.win_rate * stats.avg_win - (1 - stats.win_rate) * stats.avg_loss
        )

        # Update drawdown
        if stats.total_pnl > stats.peak_equity:
            stats.peak_equity = stats.total_pnl
            stats.current_drawdown = 0
        else:
            stats.current_drawdown = (
                (stats.peak_equity - stats.total_pnl) / max(stats.peak_equity, 1)
            ) * 100
            stats.max_drawdown = max(stats.max_drawdown, stats.current_drawdown)

        # Update averages
        self._update_rolling_averages(stats)

        # Update regime stats
        regime = record.regime
        if regime not in stats.stats_by_regime:
            stats.stats_by_regime[regime] = {
                "trades": 0,
                "wins": 0,
                "pnl": 0,
            }

        stats.stats_by_regime[regime]["trades"] += 1
        if record.pnl > 0:
            stats.stats_by_regime[regime]["wins"] += 1
        stats.stats_by_regime[regime]["pnl"] += record.pnl

        stats.last_updated = datetime.utcnow()

    def _update_rolling_averages(self, stats: StrategyStats) -> None:
        """Update rolling average metrics."""
        # Get recent trades for this strategy
        strategy_trades = [
            t for t in self._trade_history[-100:]
            if t.strategy_name == stats.name
        ]

        if not strategy_trades:
            return

        # Last 10 trades
        last_10 = strategy_trades[-10:]
        stats.last_10_trades_pnl = sum(t.pnl for t in last_10)
        stats.last_10_win_rate = (
            sum(1 for t in last_10 if t.pnl > 0) / len(last_10)
        )

        # Averages
        stats.avg_holding_time_minutes = sum(
            t.holding_time_minutes for t in strategy_trades
        ) / len(strategy_trades)
        stats.avg_mfe = sum(t.mfe for t in strategy_trades) / len(strategy_trades)
        stats.avg_mae = sum(t.mae for t in strategy_trades) / len(strategy_trades)

    def _check_retrain_triggers(self) -> Optional[str]:
        """Check if model retraining should be triggered."""
        now = datetime.utcnow()

        # Time-based trigger
        if self._last_retrain_time:
            days_since = (now - self._last_retrain_time).days
            if days_since >= self.config.retrain_interval_days:
                return f"Scheduled retrain (last: {days_since} days ago)"

        # Trade count trigger
        total_trades = len(self._trade_history)
        if total_trades >= self.config.min_trades_for_retrain:
            if self._last_retrain_time is None:
                return f"Minimum trades reached ({total_trades})"

        # Performance degradation trigger
        for name, stats in self._strategy_stats.items():
            if stats.current_drawdown >= self.config.retrain_on_drawdown_percent:
                return f"Strategy {name} drawdown ({stats.current_drawdown:.1f}%)"

        return None

    async def trigger_retrain(self, reason: str) -> None:
        """Trigger model retraining."""
        self.logger.info(f"Model retrain triggered: {reason}")

        # Publish retrain event
        self.publish_event(
            Event(
                event_type=EventType.MODEL_RETRAIN_TRIGGERED,
                data={
                    "reason": reason,
                    "trade_count": len(self._trade_history),
                    "strategies": list(self._strategy_stats.keys()),
                },
            )
        )

        self._last_retrain_time = datetime.utcnow()

    async def _load_history(self) -> None:
        """Load trade history from disk."""
        # In production, would load from file/database
        pass

    async def _save_history(self) -> None:
        """Save trade history to disk."""
        # In production, would save to file/database
        pass

    def _on_order_filled(self, event: Event) -> None:
        """Handle order filled event."""
        # Processing happens in main process method
        pass

    def _on_position_closed(self, event: Event) -> None:
        """Handle position closed event."""
        # Processing happens in main process method
        pass

    def get_strategy_stats(self, name: str) -> Optional[StrategyStats]:
        """Get statistics for a strategy."""
        return self._strategy_stats.get(name)

    def get_all_stats(self) -> dict[str, StrategyStats]:
        """Get all strategy statistics."""
        return self._strategy_stats.copy()

    def get_trade_history(
        self,
        strategy: Optional[str] = None,
        limit: int = 100,
    ) -> list[TradeRecord]:
        """Get trade history with optional filtering."""
        trades = self._trade_history

        if strategy:
            trades = [t for t in trades if t.strategy_name == strategy]

        return trades[-limit:]

    def get_status(self) -> dict[str, Any]:
        """Get feedback agent status."""
        return {
            "agent": self.name,
            "state": self.state.value,
            "total_trades": len(self._trade_history),
            "pending_trades": len(self._pending_trades),
            "strategies_tracked": len(self._strategy_stats),
            "last_retrain": (
                self._last_retrain_time.isoformat()
                if self._last_retrain_time
                else None
            ),
            "strategy_summaries": {
                name: {
                    "trades": stats.total_trades,
                    "win_rate": f"{stats.win_rate:.1%}",
                    "pnl": f"${stats.total_pnl:.2f}",
                    "drawdown": f"{stats.current_drawdown:.1f}%",
                }
                for name, stats in self._strategy_stats.items()
            },
            "metrics": self.metrics.model_dump(),
        }
