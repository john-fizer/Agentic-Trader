"""
Trend Following Strategy

A classic trend-following strategy that:
- Uses moving average crossovers to identify trends
- Confirms trends with ADX
- Enters on pullbacks within the trend
- Uses ATR-based stops
"""

from datetime import datetime
from typing import Any, Optional

import numpy as np
from loguru import logger

from src.agents.strategy.base_strategy import (
    BaseStrategy,
    StrategyConfig,
    StrategyStyle,
)
from src.core.market_state import (
    MarketStateObject,
    Regime,
    TrendBias,
)
from src.core.trade import CandidateTrade, Side, TradeTimeframe


class TrendFollowingConfig(StrategyConfig):
    """Configuration for trend following strategy."""

    name: str = "trend_following"
    style: StrategyStyle = StrategyStyle.TREND_FOLLOWING
    allowed_regimes: list[Regime] = [Regime.TRENDING]

    # Strategy parameters
    ma_fast: int = 10
    ma_slow: int = 50
    adx_threshold: float = 25.0
    trend_confirmation_bars: int = 3
    pullback_threshold: float = 0.5  # % pullback to MA


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend following strategy using moving average crossovers.

    Entry conditions:
    - Fast MA above slow MA (uptrend) or below (downtrend)
    - ADX above threshold confirming trend strength
    - Price pulls back to fast MA
    - Trend bias from MSO confirms direction

    Exit conditions:
    - Price crosses slow MA against position
    - ADX drops below threshold
    - Stop loss hit
    """

    def __init__(self, config: Optional[TrendFollowingConfig] = None) -> None:
        if config is None:
            config = TrendFollowingConfig()
        super().__init__(config)
        self.config: TrendFollowingConfig = config

    async def generate_signals(
        self,
        mso: MarketStateObject,
        symbols: list[str],
        features: dict[str, dict[str, float]],
    ) -> list[CandidateTrade]:
        """Generate trend-following signals."""
        signals = []

        for symbol in symbols:
            if symbol not in features:
                continue

            feat = features[symbol]

            # Check basic feature requirements
            required_features = ["sma_10", "sma_50", "adx_14", "atr_14"]
            if not all(f in feat for f in required_features):
                continue

            # Get instrument state from MSO
            instrument = mso.get_instrument(symbol)

            # Determine trend direction
            ma_fast = feat.get(f"sma_{self.config.ma_fast}", feat.get("sma_10", 0))
            ma_slow = feat.get(f"sma_{self.config.ma_slow}", feat.get("sma_50", 0))
            adx = feat.get("adx_14", 0)

            if ma_slow == 0:
                continue

            # Check trend strength
            if adx < self.config.adx_threshold:
                continue

            # Determine direction
            is_uptrend = ma_fast > ma_slow
            is_downtrend = ma_fast < ma_slow

            # Get current price
            current_price = feat.get("sma_10", 0)  # Approximate with short MA
            if instrument and instrument.last_price:
                current_price = instrument.last_price

            if current_price == 0:
                continue

            # Check for pullback to fast MA
            price_vs_ma = feat.get(f"price_vs_sma_{self.config.ma_fast}", 0)

            # Generate signal
            signal = None

            if is_uptrend:
                # Look for pullback to fast MA in uptrend
                if -self.config.pullback_threshold <= price_vs_ma * 100 <= 0.5:
                    # Confirm with MSO trend bias
                    if instrument and instrument.trend_bias in [
                        TrendBias.STRONG_UP,
                        TrendBias.WEAK_UP,
                    ]:
                        signal = self._create_long_signal(
                            symbol, current_price, feat, ma_fast, adx
                        )

            elif is_downtrend:
                # Look for rally to fast MA in downtrend
                if -0.5 <= price_vs_ma * 100 <= self.config.pullback_threshold:
                    # Confirm with MSO trend bias
                    if instrument and instrument.trend_bias in [
                        TrendBias.STRONG_DOWN,
                        TrendBias.WEAK_DOWN,
                    ]:
                        signal = self._create_short_signal(
                            symbol, current_price, feat, ma_fast, adx
                        )

            if signal:
                signals.append(signal)

        return signals

    def _create_long_signal(
        self,
        symbol: str,
        price: float,
        features: dict[str, float],
        ma_fast: float,
        adx: float,
    ) -> CandidateTrade:
        """Create a long signal."""
        atr = features.get("atr_14", price * 0.02)

        # Entry slightly above current price
        entry_price = price * 1.001

        # Stop 2 ATR below entry
        stop_loss = entry_price - (2 * atr)

        # Target 3 ATR above entry
        take_profit = entry_price + (3 * atr)

        # Signal strength based on ADX
        signal_strength = min(1.0, (adx - self.config.adx_threshold) / 25 + 0.5)

        return self.create_candidate_trade(
            symbol=symbol,
            side=Side.BUY,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_strength=signal_strength,
            entry_reason=f"Uptrend pullback to {self.config.ma_fast} MA, ADX={adx:.1f}",
            setup_type="trend_pullback_long",
            features=features,
        )

    def _create_short_signal(
        self,
        symbol: str,
        price: float,
        features: dict[str, float],
        ma_fast: float,
        adx: float,
    ) -> CandidateTrade:
        """Create a short signal."""
        atr = features.get("atr_14", price * 0.02)

        # Entry slightly below current price
        entry_price = price * 0.999

        # Stop 2 ATR above entry
        stop_loss = entry_price + (2 * atr)

        # Target 3 ATR below entry
        take_profit = entry_price - (3 * atr)

        # Signal strength based on ADX
        signal_strength = min(1.0, (adx - self.config.adx_threshold) / 25 + 0.5)

        return self.create_candidate_trade(
            symbol=symbol,
            side=Side.SELL,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_strength=signal_strength,
            entry_reason=f"Downtrend rally to {self.config.ma_fast} MA, ADX={adx:.1f}",
            setup_type="trend_pullback_short",
            features=features,
        )

    async def should_exit(
        self,
        mso: MarketStateObject,
        symbol: str,
        entry_price: float,
        current_price: float,
        side: Side,
        features: dict[str, float],
    ) -> tuple[bool, str]:
        """Check if position should be exited."""
        # Get MAs
        ma_slow = features.get(f"sma_{self.config.ma_slow}", features.get("sma_50", 0))
        adx = features.get("adx_14", 0)

        if ma_slow == 0:
            return False, ""

        # Exit if trend strength drops
        if adx < self.config.adx_threshold * 0.7:
            return True, f"ADX dropped below threshold ({adx:.1f})"

        # Exit on MA cross
        if side == Side.BUY:
            # Exit long if price crosses below slow MA
            if current_price < ma_slow:
                return True, "Price crossed below slow MA"
        else:
            # Exit short if price crosses above slow MA
            if current_price > ma_slow:
                return True, "Price crossed above slow MA"

        # Check regime change
        if mso.regime != Regime.TRENDING:
            return True, f"Regime changed to {mso.regime.value}"

        return False, ""
