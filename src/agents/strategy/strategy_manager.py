"""
Strategy Manager - Coordinates multiple strategy instances.

The Strategy Manager:
- Loads and manages multiple strategy instances
- Routes market data to appropriate strategies
- Aggregates candidate trades from all strategies
- Enforces strategy-level constraints
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from loguru import logger

from src.agents.base import AgentConfig, BaseAgent
from src.core.events import EventBus
from src.core.market_state import AssetClass, MarketStateObject
from src.core.trade import CandidateTrade

from src.agents.strategy.base_strategy import BaseStrategy, StrategyConfig


class StrategyManagerConfig(AgentConfig):
    """Configuration for the Strategy Manager."""

    name: str = "strategy"

    # Maximum trades per cycle
    max_candidates_per_cycle: int = 10

    # Strategy-specific configs loaded from YAML
    strategies_config_path: str = "config/strategies.yml"

    # Default symbols to track per asset class
    default_symbols: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "equities": ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
            "futures": ["ES", "NQ", "CL", "GC"],
            "crypto": ["BTC/USDT", "ETH/USDT"],
        }
    )


class StrategyManager(BaseAgent):
    """
    Manages and coordinates multiple trading strategies.

    Acts as the "Strategy Agent" in the D.A.T.A. architecture by
    aggregating signals from all registered strategies.
    """

    def __init__(
        self,
        config: StrategyManagerConfig,
        event_bus: EventBus,
        feature_engine: Optional[Any] = None,
    ) -> None:
        super().__init__(config, event_bus)
        self.config: StrategyManagerConfig = config
        self.feature_engine = feature_engine

        # Strategy registry
        self._strategies: dict[str, BaseStrategy] = {}

        # Feature cache
        self._feature_cache: dict[str, dict[str, float]] = {}
        self._cache_timestamp: Optional[datetime] = None

    async def initialize(self) -> None:
        """Initialize the Strategy Manager."""
        self.logger.info("Initializing Strategy Manager")

        # Load strategy configurations from YAML (in production)
        # For now, strategies are registered programmatically
        self.logger.info(
            f"Strategy Manager ready with {len(self._strategies)} strategies"
        )

    async def shutdown(self) -> None:
        """Shutdown the Strategy Manager."""
        self.logger.info("Shutting down Strategy Manager")

    def register_strategy(self, strategy: BaseStrategy) -> None:
        """Register a strategy with the manager."""
        self._strategies[strategy.name] = strategy
        self.logger.info(f"Registered strategy: {strategy.name}")

    def unregister_strategy(self, name: str) -> None:
        """Unregister a strategy."""
        if name in self._strategies:
            del self._strategies[name]
            self.logger.info(f"Unregistered strategy: {name}")

    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        """Get a strategy by name."""
        return self._strategies.get(name)

    def list_strategies(self) -> list[str]:
        """List all registered strategy names."""
        return list(self._strategies.keys())

    async def process(
        self, mso: MarketStateObject, **kwargs: Any
    ) -> list[CandidateTrade]:
        """
        Generate candidate trades from all active strategies.

        Args:
            mso: Current Market State Object
            **kwargs: Additional data (price_data, features, etc.)

        Returns:
            List of candidate trades from all strategies
        """
        all_candidates: list[CandidateTrade] = []

        # Get symbols to analyze
        symbols = kwargs.get("symbols", self._get_default_symbols(mso))

        # Compute features (or use cached)
        features = await self._get_features(symbols, kwargs.get("price_data", {}))

        # Run each active strategy
        for name, strategy in self._strategies.items():
            if not strategy.is_active:
                continue

            # Check if strategy can trade in current regime
            if not strategy.can_trade_regime(mso):
                self.logger.debug(
                    f"Strategy {name} skipped - regime incompatible"
                )
                continue

            try:
                # Generate signals
                candidates = await strategy.generate_signals(mso, symbols, features)

                # Filter signals
                filtered = strategy.filter_signals(candidates, mso)

                if filtered:
                    self.logger.info(
                        f"Strategy {name} generated {len(filtered)} signals"
                    )
                    all_candidates.extend(filtered)

            except Exception as e:
                self.logger.error(f"Strategy {name} error: {e}")

        # Sort by signal strength and limit
        all_candidates.sort(key=lambda x: x.signal_strength, reverse=True)
        all_candidates = all_candidates[: self.config.max_candidates_per_cycle]

        self.logger.info(
            f"Total candidates from all strategies: {len(all_candidates)}"
        )

        return all_candidates

    async def check_exits(
        self,
        mso: MarketStateObject,
        positions: list[dict],
        price_data: dict,
    ) -> list[tuple[str, str]]:
        """
        Check if any positions should be exited based on strategy rules.

        Args:
            mso: Current Market State Object
            positions: List of current positions
            price_data: Current price data

        Returns:
            List of (position_id, exit_reason) tuples
        """
        exits = []
        features = await self._get_features(
            [p["symbol"] for p in positions], price_data
        )

        for position in positions:
            strategy_name = position.get("strategy_name")
            if strategy_name not in self._strategies:
                continue

            strategy = self._strategies[strategy_name]
            symbol = position["symbol"]

            try:
                should_exit, reason = await strategy.should_exit(
                    mso=mso,
                    symbol=symbol,
                    entry_price=position["entry_price"],
                    current_price=price_data.get(symbol, {}).get("last", 0),
                    side=position["side"],
                    features=features.get(symbol, {}),
                )

                if should_exit:
                    exits.append((position["id"], reason))

            except Exception as e:
                self.logger.error(
                    f"Exit check error for {symbol}: {e}"
                )

        return exits

    def _get_default_symbols(self, mso: MarketStateObject) -> list[str]:
        """Get default symbols based on session and asset class."""
        symbols = []

        # Get symbols from MSO instruments
        if mso.instruments:
            symbols.extend(mso.instruments.keys())

        # Add defaults if empty
        if not symbols:
            for asset_symbols in self.config.default_symbols.values():
                symbols.extend(asset_symbols)

        return list(set(symbols))

    async def _get_features(
        self,
        symbols: list[str],
        price_data: dict,
    ) -> dict[str, dict[str, float]]:
        """
        Get features for symbols.

        Uses feature engine if available, otherwise returns empty dict.
        """
        if self.feature_engine:
            return await self.feature_engine.compute_features(symbols, price_data)

        # Cache check
        now = datetime.utcnow()
        if (
            self._cache_timestamp
            and (now - self._cache_timestamp).total_seconds() < 60
        ):
            return self._feature_cache

        # Compute basic features inline
        features = {}
        for symbol in symbols:
            if symbol in price_data:
                features[symbol] = self._compute_basic_features(
                    price_data[symbol]
                )
            else:
                features[symbol] = {}

        self._feature_cache = features
        self._cache_timestamp = now

        return features

    def _compute_basic_features(self, data: dict) -> dict[str, float]:
        """Compute basic features from price data."""
        features = {}

        prices = data.get("close", [])
        if len(prices) < 20:
            return features

        import numpy as np

        # Returns
        returns = np.diff(prices) / prices[:-1]
        features["return_1d"] = returns[-1] if len(returns) > 0 else 0
        features["return_5d"] = (
            (prices[-1] - prices[-5]) / prices[-5] if len(prices) > 5 else 0
        )
        features["return_20d"] = (
            (prices[-1] - prices[-20]) / prices[-20] if len(prices) > 20 else 0
        )

        # Volatility
        features["volatility_20d"] = float(np.std(returns[-20:]) * np.sqrt(252))

        # Moving averages
        features["sma_10"] = float(np.mean(prices[-10:]))
        features["sma_20"] = float(np.mean(prices[-20:]))
        features["price_vs_sma10"] = (prices[-1] - features["sma_10"]) / features["sma_10"]
        features["price_vs_sma20"] = (prices[-1] - features["sma_20"]) / features["sma_20"]

        # Momentum
        if len(prices) >= 14:
            gains = [max(0, returns[i]) for i in range(-14, 0)]
            losses = [abs(min(0, returns[i])) for i in range(-14, 0)]
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses) if np.mean(losses) > 0 else 0.0001
            rs = avg_gain / avg_loss
            features["rsi_14"] = 100 - (100 / (1 + rs))

        return features

    def get_status(self) -> dict[str, Any]:
        """Get strategy manager status."""
        return {
            "agent": self.name,
            "state": self.state.value,
            "strategies": {
                name: strategy.get_status()
                for name, strategy in self._strategies.items()
            },
            "metrics": self.metrics.model_dump(),
        }
