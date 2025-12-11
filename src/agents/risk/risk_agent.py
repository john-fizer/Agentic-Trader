"""
Risk & Portfolio Agent - Enforces risk limits and allocates capital.

The Risk Agent is responsible for:
- Evaluating candidate trades under defined risk rules
- Adjusting position sizes based on strategy performance and market conditions
- Enforcing portfolio-level constraints (exposure, concentration, heat)
- Triggering circuit breakers when limits are exceeded
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from loguru import logger

from src.agents.base import AgentConfig, BaseAgent
from src.core.events import Event, EventBus, EventType, RiskEvent
from src.core.market_state import MarketStateObject, Regime, Volatility
from src.core.trade import (
    CandidateTrade,
    Order,
    OrderType,
    PortfolioSnapshot,
    Position,
    PositionSide,
    Side,
)


class RiskLimits(BaseModel):
    """Risk limits configuration."""

    # Per-trade limits
    max_risk_per_trade_percent: float = 1.0  # Max risk per trade as % of equity
    max_risk_per_trade_amount: Optional[float] = None  # Absolute max risk

    # Portfolio limits
    max_portfolio_heat_percent: float = 6.0  # Sum of all open risk
    max_gross_exposure_percent: float = 200.0  # Long + Short as % of equity
    max_net_exposure_percent: float = 100.0  # Long - Short as % of equity
    max_long_exposure_percent: float = 150.0
    max_short_exposure_percent: float = 100.0

    # Position limits
    max_positions: int = 20
    max_position_size_percent: float = 10.0  # Max single position
    max_correlated_positions: int = 5  # Max positions in same sector/asset

    # Concentration limits
    max_sector_exposure_percent: float = 30.0
    max_single_name_exposure_percent: float = 15.0

    # Drawdown limits
    max_daily_drawdown_percent: float = 3.0
    max_weekly_drawdown_percent: float = 5.0
    strategy_pause_drawdown_percent: float = 10.0  # Pause strategy after this DD


class RiskAgentConfig(AgentConfig):
    """Configuration for the Risk Agent."""

    name: str = "risk"
    limits: RiskLimits = Field(default_factory=RiskLimits)

    # Sizing parameters
    use_kelly_sizing: bool = False
    kelly_fraction: float = 0.25  # Fraction of full Kelly to use
    min_position_size: float = 100.0  # Minimum position value

    # Regime adjustments
    reduce_size_in_high_vol: bool = True
    high_vol_size_multiplier: float = 0.5
    reduce_size_in_choppy: bool = True
    choppy_size_multiplier: float = 0.75


class PortfolioState(BaseModel):
    """Current portfolio state tracked by risk agent."""

    total_equity: float = 100000.0
    cash: float = 100000.0

    # Exposure
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    long_exposure: float = 0.0
    short_exposure: float = 0.0

    # Risk metrics
    portfolio_heat: float = 0.0  # Sum of $ at risk
    portfolio_heat_percent: float = 0.0

    # Position tracking
    num_positions: int = 0
    positions: list[Position] = Field(default_factory=list)

    # Sector exposure
    sector_exposure: dict[str, float] = Field(default_factory=dict)

    # PnL tracking
    daily_pnl: float = 0.0
    daily_pnl_percent: float = 0.0
    weekly_pnl: float = 0.0
    weekly_pnl_percent: float = 0.0

    # Strategy tracking
    strategy_pnl: dict[str, float] = Field(default_factory=dict)
    strategy_drawdown: dict[str, float] = Field(default_factory=dict)


class RiskAgent(BaseAgent):
    """
    The Risk Agent evaluates trades and enforces portfolio risk limits.

    It acts as a gatekeeper between strategy signals and execution,
    ensuring the portfolio stays within defined risk parameters.
    """

    def __init__(
        self,
        config: RiskAgentConfig,
        event_bus: EventBus,
    ) -> None:
        super().__init__(config, event_bus)
        self.config: RiskAgentConfig = config
        self.portfolio_state = PortfolioState()

        # Strategy performance tracking for adaptive sizing
        self._strategy_performance: dict[str, dict[str, float]] = {}

        # Paused strategies
        self._paused_strategies: set[str] = set()

    async def initialize(self) -> None:
        """Initialize the Risk Agent."""
        self.logger.info("Initializing Risk Agent")
        self.logger.info("Risk Agent ready")

    async def shutdown(self) -> None:
        """Shutdown the Risk Agent."""
        self.logger.info("Shutting down Risk Agent")

    async def process(
        self, mso: MarketStateObject, **kwargs: Any
    ) -> list[CandidateTrade]:
        """
        Evaluate candidate trades and return approved trades with position sizes.

        Args:
            mso: Current Market State Object
            candidate_trades: List of candidate trades from strategies

        Returns:
            List of approved trades with proper sizing
        """
        candidate_trades: list[CandidateTrade] = kwargs.get("candidate_trades", [])

        if not candidate_trades:
            return []

        approved_trades: list[CandidateTrade] = []

        # Update portfolio state
        if "portfolio" in kwargs:
            self._update_portfolio_state(kwargs["portfolio"])

        # Check portfolio-level limits first
        portfolio_ok, portfolio_reason = self._check_portfolio_limits()
        if not portfolio_ok:
            self.logger.warning(f"Portfolio limit breach: {portfolio_reason}")
            self._publish_risk_event("warning", "portfolio_limit", portfolio_reason)
            return []

        # Evaluate each candidate trade
        for trade in candidate_trades:
            # Skip trades from paused strategies
            if trade.strategy_name in self._paused_strategies:
                self.logger.debug(f"Skipping trade from paused strategy: {trade.strategy_name}")
                continue

            # Evaluate trade
            approved, reason = self._evaluate_trade(trade, mso)

            if approved:
                # Calculate position size
                sized_trade = self._size_trade(trade, mso)
                if sized_trade:
                    approved_trades.append(sized_trade)
                    self.logger.info(
                        f"Approved: {trade.symbol} {trade.side.value} "
                        f"size={sized_trade.suggested_size:.2f}"
                    )
            else:
                self.logger.debug(f"Rejected {trade.symbol}: {reason}")

        return approved_trades

    def _check_portfolio_limits(self) -> tuple[bool, str]:
        """Check if portfolio is within limits."""
        limits = self.config.limits
        state = self.portfolio_state

        # Check position count
        if state.num_positions >= limits.max_positions:
            return False, f"Max positions ({limits.max_positions}) reached"

        # Check gross exposure
        gross_pct = (state.gross_exposure / state.total_equity) * 100
        if gross_pct >= limits.max_gross_exposure_percent:
            return False, f"Gross exposure {gross_pct:.1f}% exceeds limit"

        # Check net exposure
        net_pct = (state.net_exposure / state.total_equity) * 100
        if abs(net_pct) >= limits.max_net_exposure_percent:
            return False, f"Net exposure {net_pct:.1f}% exceeds limit"

        # Check portfolio heat
        if state.portfolio_heat_percent >= limits.max_portfolio_heat_percent:
            return False, f"Portfolio heat {state.portfolio_heat_percent:.1f}% exceeds limit"

        # Check daily drawdown
        if state.daily_pnl_percent <= -limits.max_daily_drawdown_percent:
            return False, f"Daily drawdown {state.daily_pnl_percent:.1f}% exceeds limit"

        return True, "OK"

    def _evaluate_trade(
        self, trade: CandidateTrade, mso: MarketStateObject
    ) -> tuple[bool, str]:
        """Evaluate a single candidate trade."""
        limits = self.config.limits

        # Check if we can open position in this symbol
        can_open, reason = mso.can_open_new_position(
            trade.symbol,
            trade.timeframe,
        )
        if not can_open:
            return False, reason

        # Check symbol concentration
        existing_exposure = self._get_symbol_exposure(trade.symbol)
        if existing_exposure > 0:
            exposure_pct = (existing_exposure / self.portfolio_state.total_equity) * 100
            if exposure_pct >= limits.max_single_name_exposure_percent:
                return False, f"Single name exposure limit reached for {trade.symbol}"

        # Validate stop loss
        if trade.stop_loss is None:
            return False, "No stop loss defined"

        # Check reward/risk ratio
        if trade.reward_risk_ratio and trade.reward_risk_ratio < 1.0:
            return False, f"R:R ratio {trade.reward_risk_ratio:.2f} below minimum"

        # Check correlation/sector limits (simplified)
        # In production, would check actual correlations
        sector = self._get_sector(trade.symbol)
        if sector:
            sector_exposure = self.portfolio_state.sector_exposure.get(sector, 0)
            sector_pct = (sector_exposure / self.portfolio_state.total_equity) * 100
            if sector_pct >= limits.max_sector_exposure_percent:
                return False, f"Sector {sector} exposure limit reached"

        return True, "OK"

    def _size_trade(
        self, trade: CandidateTrade, mso: MarketStateObject
    ) -> Optional[CandidateTrade]:
        """Calculate position size for a trade."""
        limits = self.config.limits
        equity = self.portfolio_state.total_equity

        # Base risk per trade
        max_risk_pct = limits.max_risk_per_trade_percent

        # Adjust for regime
        size_multiplier = 1.0

        if self.config.reduce_size_in_high_vol and mso.volatility == Volatility.HIGH:
            size_multiplier *= self.config.high_vol_size_multiplier

        if self.config.reduce_size_in_choppy and mso.regime == Regime.CHOPPY:
            size_multiplier *= self.config.choppy_size_multiplier

        # Apply playbook multiplier
        size_multiplier *= mso.allowed_playbooks.max_position_size_multiplier

        # Adjust for strategy performance (optional Kelly-style)
        if self.config.use_kelly_sizing:
            kelly_mult = self._get_kelly_multiplier(trade.strategy_name)
            size_multiplier *= kelly_mult

        # Adjust for signal strength
        size_multiplier *= trade.signal_strength

        # Calculate risk amount
        risk_percent = max_risk_pct * size_multiplier
        risk_amount = equity * (risk_percent / 100)

        # Apply absolute limit if set
        if limits.max_risk_per_trade_amount:
            risk_amount = min(risk_amount, limits.max_risk_per_trade_amount)

        # Calculate position size from risk and stop distance
        entry_price = trade.entry_price or 0
        if entry_price == 0:
            # For market orders, we'd need to estimate entry
            return None

        if trade.side == Side.BUY:
            stop_distance = entry_price - trade.stop_loss
        else:
            stop_distance = trade.stop_loss - entry_price

        if stop_distance <= 0:
            self.logger.warning(f"Invalid stop distance for {trade.symbol}")
            return None

        # Position size (shares/units)
        position_size = risk_amount / stop_distance

        # Check minimum size
        position_value = position_size * entry_price
        if position_value < self.config.min_position_size:
            self.logger.debug(f"Position size {position_value:.2f} below minimum")
            return None

        # Check maximum size
        max_position_value = equity * (limits.max_position_size_percent / 100)
        if position_value > max_position_value:
            position_size = max_position_value / entry_price

        # Update trade with sizing
        trade.suggested_size = position_size
        trade.risk_amount = risk_amount
        trade.risk_percent = risk_percent

        return trade

    def _get_kelly_multiplier(self, strategy_name: str) -> float:
        """Calculate Kelly-based size multiplier for a strategy."""
        if strategy_name not in self._strategy_performance:
            return 1.0

        perf = self._strategy_performance[strategy_name]
        win_rate = perf.get("win_rate", 0.5)
        avg_win = perf.get("avg_win", 1.0)
        avg_loss = perf.get("avg_loss", 1.0)

        if avg_loss == 0:
            return 1.0

        # Kelly criterion
        win_loss_ratio = avg_win / avg_loss
        kelly = win_rate - (1 - win_rate) / win_loss_ratio

        # Use fraction of Kelly
        kelly_fraction = max(0, min(kelly * self.config.kelly_fraction, 1.0))

        return max(0.25, kelly_fraction)  # Minimum 25% of base size

    def _get_symbol_exposure(self, symbol: str) -> float:
        """Get current exposure to a symbol."""
        return sum(
            abs(p.market_value)
            for p in self.portfolio_state.positions
            if p.symbol == symbol and p.is_open
        )

    def _get_sector(self, symbol: str) -> Optional[str]:
        """Get sector for a symbol (simplified)."""
        # In production, would look up actual sector
        sector_map = {
            "AAPL": "technology",
            "MSFT": "technology",
            "GOOGL": "technology",
            "AMZN": "consumer",
            "NVDA": "technology",
            "JPM": "financials",
            "BAC": "financials",
            "XOM": "energy",
            "CVX": "energy",
        }
        return sector_map.get(symbol)

    def _update_portfolio_state(self, portfolio: PortfolioSnapshot) -> None:
        """Update internal portfolio state from snapshot."""
        self.portfolio_state.total_equity = portfolio.total_equity
        self.portfolio_state.cash = portfolio.cash
        self.portfolio_state.gross_exposure = portfolio.total_exposure
        self.portfolio_state.net_exposure = portfolio.net_exposure
        self.portfolio_state.long_exposure = portfolio.long_exposure
        self.portfolio_state.short_exposure = portfolio.short_exposure
        self.portfolio_state.num_positions = portfolio.num_positions
        self.portfolio_state.positions = portfolio.positions
        self.portfolio_state.portfolio_heat = portfolio.portfolio_heat
        self.portfolio_state.portfolio_heat_percent = (
            (portfolio.portfolio_heat / portfolio.total_equity) * 100
            if portfolio.total_equity > 0
            else 0
        )
        self.portfolio_state.daily_pnl = portfolio.daily_pnl
        self.portfolio_state.daily_pnl_percent = portfolio.daily_pnl_percent

    def _publish_risk_event(
        self, severity: str, metric: str, message: str
    ) -> None:
        """Publish a risk event."""
        event = RiskEvent(
            event_type=EventType.RISK_LIMIT_BREACH,
            severity=severity,
            metric=metric,
            message=message,
            data={"portfolio_state": self.portfolio_state.model_dump()},
        )
        self.publish_event(event)

    def update_strategy_performance(
        self, strategy_name: str, metrics: dict[str, float]
    ) -> None:
        """Update performance metrics for a strategy."""
        self._strategy_performance[strategy_name] = metrics

        # Check if strategy should be paused
        drawdown = metrics.get("drawdown", 0)
        if abs(drawdown) >= self.config.limits.strategy_pause_drawdown_percent:
            self.pause_strategy(strategy_name, f"Drawdown {drawdown:.1f}%")

    def pause_strategy(self, strategy_name: str, reason: str) -> None:
        """Pause a strategy."""
        self._paused_strategies.add(strategy_name)
        self.logger.warning(f"Strategy {strategy_name} paused: {reason}")

    def resume_strategy(self, strategy_name: str) -> None:
        """Resume a paused strategy."""
        self._paused_strategies.discard(strategy_name)
        self.logger.info(f"Strategy {strategy_name} resumed")

    def get_status(self) -> dict[str, Any]:
        """Get risk agent status."""
        return {
            "agent": self.name,
            "state": self.state.value,
            "portfolio_state": self.portfolio_state.model_dump(),
            "paused_strategies": list(self._paused_strategies),
            "limits": self.config.limits.model_dump(),
            "metrics": self.metrics.model_dump(),
        }
