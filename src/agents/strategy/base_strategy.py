"""
Base Strategy class for all trading strategies.

Provides the interface and common functionality for strategy implementations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from loguru import logger

from src.core.market_state import (
    AssetClass,
    MarketStateObject,
    Regime,
    Timeframe,
    TrendBias,
)
from src.core.trade import CandidateTrade, Side, TradeTimeframe


class StrategyStyle(str, Enum):
    """Strategy style classification."""

    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    BREAKOUT = "breakout"
    SPREAD = "spread"
    ARBITRAGE = "arbitrage"


class StrategyStatus(str, Enum):
    """Strategy operational status."""

    ACTIVE = "active"
    PAUSED = "paused"
    PAPER_ONLY = "paper_only"
    RETIRED = "retired"


class StrategyConfig(BaseModel):
    """Configuration for a trading strategy."""

    name: str
    version: str = "1.0.0"
    enabled: bool = True
    status: StrategyStatus = StrategyStatus.ACTIVE

    # Strategy classification
    style: StrategyStyle = StrategyStyle.TREND_FOLLOWING
    asset_classes: list[AssetClass] = Field(default_factory=lambda: [AssetClass.EQUITIES])
    timeframes: list[TradeTimeframe] = Field(default_factory=lambda: [TradeTimeframe.INTRADAY])

    # Risk parameters
    max_position_size_percent: float = 5.0  # Max position as % of equity
    default_stop_percent: float = 2.0  # Default stop loss distance
    default_target_percent: float = 4.0  # Default take profit distance
    min_reward_risk: float = 1.5  # Minimum reward/risk ratio

    # Regime compatibility
    allowed_regimes: list[Regime] = Field(
        default_factory=lambda: [Regime.TRENDING, Regime.CHOPPY, Regime.MEAN_REVERTING]
    )
    avoid_panic: bool = True

    # Signal parameters
    min_signal_strength: float = 0.5
    cooldown_minutes: int = 30  # Min time between signals for same symbol


class StrategyMetrics(BaseModel):
    """Performance metrics for a strategy."""

    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # PnL
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    # Ratios
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr_realized: float = 0.0

    # Risk metrics
    max_drawdown: float = 0.0
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None

    # Regime-specific
    pnl_by_regime: dict[str, float] = Field(default_factory=dict)
    win_rate_by_regime: dict[str, float] = Field(default_factory=dict)

    # Timestamps
    last_trade_time: Optional[datetime] = None
    last_win_time: Optional[datetime] = None
    last_loss_time: Optional[datetime] = None


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Each strategy must implement:
    - generate_signals(): Produces candidate trades from market data
    - should_exit(): Determines if existing position should be closed

    Strategies receive the MSO and can access all relevant market context.
    """

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.metrics = StrategyMetrics()
        self.logger = logger.bind(strategy=config.name)

        # Signal cooldown tracking
        self._last_signal_time: dict[str, datetime] = {}

    @property
    def name(self) -> str:
        """Strategy name."""
        return self.config.name

    @property
    def is_active(self) -> bool:
        """Check if strategy is active."""
        return self.config.enabled and self.config.status == StrategyStatus.ACTIVE

    @abstractmethod
    async def generate_signals(
        self,
        mso: MarketStateObject,
        symbols: list[str],
        features: dict[str, dict[str, float]],
    ) -> list[CandidateTrade]:
        """
        Generate candidate trades based on current market conditions.

        Args:
            mso: Market State Object with current conditions
            symbols: List of symbols to analyze
            features: Pre-computed features per symbol

        Returns:
            List of candidate trades (may be empty)
        """
        pass

    @abstractmethod
    async def should_exit(
        self,
        mso: MarketStateObject,
        symbol: str,
        entry_price: float,
        current_price: float,
        side: Side,
        features: dict[str, float],
    ) -> tuple[bool, str]:
        """
        Determine if an existing position should be exited.

        Args:
            mso: Market State Object
            symbol: Position symbol
            entry_price: Entry price
            current_price: Current price
            side: Position side
            features: Current features

        Returns:
            Tuple of (should_exit, reason)
        """
        pass

    def can_trade_regime(self, mso: MarketStateObject) -> bool:
        """Check if strategy can trade in current regime."""
        if self.config.avoid_panic and mso.regime == Regime.PANIC:
            return False
        return mso.regime in self.config.allowed_regimes

    def can_trade_symbol(self, mso: MarketStateObject, symbol: str) -> bool:
        """Check if strategy can trade a specific symbol."""
        # Check if symbol is in MSO
        instrument = mso.get_instrument(symbol)
        if instrument is None:
            return True  # Allow if not tracked

        if not instrument.is_tradeable:
            return False

        # Check asset class
        if instrument.asset_class not in self.config.asset_classes:
            return False

        return True

    def is_in_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in signal cooldown period."""
        if symbol not in self._last_signal_time:
            return False

        elapsed = datetime.utcnow() - self._last_signal_time[symbol]
        return elapsed.total_seconds() < self.config.cooldown_minutes * 60

    def record_signal(self, symbol: str) -> None:
        """Record a signal for cooldown tracking."""
        self._last_signal_time[symbol] = datetime.utcnow()

    def filter_signals(
        self, trades: list[CandidateTrade], mso: MarketStateObject
    ) -> list[CandidateTrade]:
        """Filter signals based on strategy constraints."""
        filtered = []
        for trade in trades:
            # Check signal strength
            if trade.signal_strength < self.config.min_signal_strength:
                continue

            # Check cooldown
            if self.is_in_cooldown(trade.symbol):
                continue

            # Check regime compatibility
            if not self.can_trade_regime(mso):
                continue

            # Check symbol tradability
            if not self.can_trade_symbol(mso, trade.symbol):
                continue

            # Check playbook restrictions
            if not self._is_playbook_allowed(mso):
                continue

            filtered.append(trade)
            self.record_signal(trade.symbol)

        return filtered

    def _is_playbook_allowed(self, mso: MarketStateObject) -> bool:
        """Check if this strategy's style is allowed by current playbook."""
        playbooks = mso.allowed_playbooks
        style = self.config.style

        style_checks = {
            StrategyStyle.TREND_FOLLOWING: playbooks.trend_following,
            StrategyStyle.MEAN_REVERSION: playbooks.mean_reversion,
            StrategyStyle.MOMENTUM: playbooks.momentum,
            StrategyStyle.VOLATILITY: playbooks.volatility,
            StrategyStyle.SPREAD: playbooks.spreads,
        }

        return style_checks.get(style, True)

    def create_candidate_trade(
        self,
        symbol: str,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: Optional[float] = None,
        signal_strength: float = 0.5,
        entry_reason: str = "",
        setup_type: str = "",
        features: Optional[dict[str, float]] = None,
    ) -> CandidateTrade:
        """Helper to create a candidate trade with strategy defaults."""
        return CandidateTrade(
            symbol=symbol,
            side=side,
            suggested_size=0.0,  # Will be set by risk agent
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timeframe=self.config.timeframes[0],
            asset_class=self.config.asset_classes[0].value,
            strategy_name=self.name,
            strategy_version=self.config.version,
            signal_strength=signal_strength,
            entry_reason=entry_reason,
            setup_type=setup_type,
            features=features or {},
        )

    def update_metrics(
        self,
        trade_pnl: float,
        regime: Regime,
    ) -> None:
        """Update strategy metrics after a trade."""
        self.metrics.total_trades += 1
        self.metrics.total_pnl += trade_pnl
        self.metrics.last_trade_time = datetime.utcnow()

        if trade_pnl > 0:
            self.metrics.winning_trades += 1
            self.metrics.gross_profit += trade_pnl
            self.metrics.largest_win = max(self.metrics.largest_win, trade_pnl)
            self.metrics.last_win_time = datetime.utcnow()
        else:
            self.metrics.losing_trades += 1
            self.metrics.gross_loss += abs(trade_pnl)
            self.metrics.largest_loss = min(self.metrics.largest_loss, trade_pnl)
            self.metrics.last_loss_time = datetime.utcnow()

        # Update ratios
        if self.metrics.total_trades > 0:
            self.metrics.win_rate = self.metrics.winning_trades / self.metrics.total_trades

        if self.metrics.gross_loss > 0:
            self.metrics.profit_factor = self.metrics.gross_profit / self.metrics.gross_loss

        if self.metrics.winning_trades > 0:
            self.metrics.avg_win = self.metrics.gross_profit / self.metrics.winning_trades

        if self.metrics.losing_trades > 0:
            self.metrics.avg_loss = self.metrics.gross_loss / self.metrics.losing_trades

        # Update regime-specific metrics
        regime_key = regime.value
        if regime_key not in self.metrics.pnl_by_regime:
            self.metrics.pnl_by_regime[regime_key] = 0.0
        self.metrics.pnl_by_regime[regime_key] += trade_pnl

    def get_status(self) -> dict[str, Any]:
        """Get strategy status."""
        return {
            "name": self.name,
            "version": self.config.version,
            "status": self.config.status.value,
            "style": self.config.style.value,
            "is_active": self.is_active,
            "metrics": self.metrics.model_dump(),
        }
