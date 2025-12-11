"""
Mean Reversion Strategy

A mean-reversion strategy that:
- Identifies oversold/overbought conditions using RSI and Bollinger Bands
- Enters when price reaches extremes
- Targets return to the mean
- Uses tight stops for quick exits on failed reversals
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
    Volatility,
)
from src.core.trade import CandidateTrade, Side, TradeTimeframe


class MeanReversionConfig(StrategyConfig):
    """Configuration for mean reversion strategy."""

    name: str = "mean_reversion"
    style: StrategyStyle = StrategyStyle.MEAN_REVERSION
    allowed_regimes: list[Regime] = [Regime.MEAN_REVERTING, Regime.CHOPPY]

    # Strategy parameters
    bb_period: int = 20
    bb_std: float = 2.0
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    min_squeeze_bars: int = 5

    # Risk parameters
    max_position_size_percent: float = 3.0
    default_stop_percent: float = 1.5
    default_target_percent: float = 2.0


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion strategy using RSI and Bollinger Bands.

    Entry conditions (long):
    - RSI below oversold threshold
    - Price at or below lower Bollinger Band
    - Regime is mean-reverting or choppy
    - No high volatility (avoids catching falling knives)

    Entry conditions (short):
    - RSI above overbought threshold
    - Price at or above upper Bollinger Band
    - Same regime and volatility conditions

    Exit conditions:
    - Price reaches middle band (mean)
    - RSI normalizes (crosses 50)
    - Stop loss hit
    """

    def __init__(self, config: Optional[MeanReversionConfig] = None) -> None:
        if config is None:
            config = MeanReversionConfig()
        super().__init__(config)
        self.config: MeanReversionConfig = config

    async def generate_signals(
        self,
        mso: MarketStateObject,
        symbols: list[str],
        features: dict[str, dict[str, float]],
    ) -> list[CandidateTrade]:
        """Generate mean-reversion signals."""
        signals = []

        # Don't trade in high volatility
        if mso.volatility == Volatility.HIGH:
            return signals

        for symbol in symbols:
            if symbol not in features:
                continue

            feat = features[symbol]

            # Check required features
            required = ["rsi_14", "bb_position", "sma_20", "atr_14"]
            if not all(f in feat for f in required):
                continue

            # Get values
            rsi = feat.get("rsi_14", 50)
            bb_position = feat.get("bb_position", 0.5)
            atr = feat.get("atr_14", 0)
            sma_20 = feat.get("sma_20", 0)

            if sma_20 == 0 or atr == 0:
                continue

            # Get instrument state
            instrument = mso.get_instrument(symbol)
            current_price = sma_20
            if instrument and instrument.last_price:
                current_price = instrument.last_price

            # Check for oversold condition (long signal)
            if rsi < self.config.rsi_oversold and bb_position < 0.1:
                # Avoid strong downtrends
                if instrument and instrument.trend_bias not in [
                    TrendBias.STRONG_DOWN,
                    TrendBias.CAPITULATION,
                ]:
                    signal = self._create_long_signal(
                        symbol, current_price, feat, sma_20, rsi, bb_position
                    )
                    if signal:
                        signals.append(signal)

            # Check for overbought condition (short signal)
            elif rsi > self.config.rsi_overbought and bb_position > 0.9:
                # Avoid strong uptrends
                if instrument and instrument.trend_bias not in [
                    TrendBias.STRONG_UP,
                ]:
                    signal = self._create_short_signal(
                        symbol, current_price, feat, sma_20, rsi, bb_position
                    )
                    if signal:
                        signals.append(signal)

        return signals

    def _create_long_signal(
        self,
        symbol: str,
        price: float,
        features: dict[str, float],
        mean: float,
        rsi: float,
        bb_pos: float,
    ) -> Optional[CandidateTrade]:
        """Create a long (buy oversold) signal."""
        atr = features.get("atr_14", price * 0.02)

        # Entry at current price
        entry_price = price

        # Stop below recent low (1.5 ATR)
        stop_loss = entry_price - (1.5 * atr)

        # Target the mean (SMA 20)
        take_profit = mean

        # Ensure positive R:R
        risk = entry_price - stop_loss
        reward = take_profit - entry_price

        if risk <= 0 or reward / risk < 1.0:
            return None

        # Signal strength based on how extreme the condition is
        rsi_extreme = (self.config.rsi_oversold - rsi) / self.config.rsi_oversold
        bb_extreme = (0.1 - bb_pos) / 0.1 if bb_pos < 0.1 else 0
        signal_strength = 0.5 + (rsi_extreme * 0.25) + (bb_extreme * 0.25)
        signal_strength = min(1.0, max(0.5, signal_strength))

        return self.create_candidate_trade(
            symbol=symbol,
            side=Side.BUY,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_strength=signal_strength,
            entry_reason=f"Oversold: RSI={rsi:.1f}, BB={bb_pos:.2f}",
            setup_type="mean_reversion_long",
            features=features,
        )

    def _create_short_signal(
        self,
        symbol: str,
        price: float,
        features: dict[str, float],
        mean: float,
        rsi: float,
        bb_pos: float,
    ) -> Optional[CandidateTrade]:
        """Create a short (sell overbought) signal."""
        atr = features.get("atr_14", price * 0.02)

        # Entry at current price
        entry_price = price

        # Stop above recent high (1.5 ATR)
        stop_loss = entry_price + (1.5 * atr)

        # Target the mean (SMA 20)
        take_profit = mean

        # Ensure positive R:R
        risk = stop_loss - entry_price
        reward = entry_price - take_profit

        if risk <= 0 or reward / risk < 1.0:
            return None

        # Signal strength based on how extreme the condition is
        rsi_extreme = (rsi - self.config.rsi_overbought) / (100 - self.config.rsi_overbought)
        bb_extreme = (bb_pos - 0.9) / 0.1 if bb_pos > 0.9 else 0
        signal_strength = 0.5 + (rsi_extreme * 0.25) + (bb_extreme * 0.25)
        signal_strength = min(1.0, max(0.5, signal_strength))

        return self.create_candidate_trade(
            symbol=symbol,
            side=Side.SELL,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_strength=signal_strength,
            entry_reason=f"Overbought: RSI={rsi:.1f}, BB={bb_pos:.2f}",
            setup_type="mean_reversion_short",
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
        rsi = features.get("rsi_14", 50)
        bb_position = features.get("bb_position", 0.5)

        if side == Side.BUY:
            # Exit long when RSI normalizes or price reaches mean
            if rsi > 50:
                return True, f"RSI normalized ({rsi:.1f})"
            if bb_position > 0.5:
                return True, "Price reached mean"

        else:  # SHORT
            # Exit short when RSI normalizes or price reaches mean
            if rsi < 50:
                return True, f"RSI normalized ({rsi:.1f})"
            if bb_position < 0.5:
                return True, "Price reached mean"

        # Exit if regime changes to trending
        if mso.regime == Regime.TRENDING:
            return True, "Regime changed to trending"

        return False, ""
