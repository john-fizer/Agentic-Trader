"""
Initializer Agent - Builds the Market State Object (MSO).

The Initializer Agent is responsible for:
- Building a contextual "job GPS" for the current market environment
- Determining the market regime (trending, mean-reverting, choppy, panic)
- Assessing volatility and liquidity conditions
- Identifying key levels and upcoming macro events
- Deciding which playbooks/strategies are allowed
- Producing human-readable summaries for monitoring
"""

from datetime import datetime, timedelta
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, Field
from loguru import logger

from src.agents.base import AgentConfig, BaseAgent
from src.core.events import EventBus
from src.core.market_state import (
    AllowedPlaybooks,
    AssetClass,
    InstrumentState,
    KeyLevels,
    Liquidity,
    MacroEvent,
    MarketStateObject,
    Regime,
    Session,
    TrendBias,
    Volatility,
)


class InitializerConfig(AgentConfig):
    """Configuration for the Initializer Agent."""

    name: str = "initializer"

    # Regime detection parameters
    regime_lookback_days: int = 20
    trending_threshold: float = 0.6  # ADX-like threshold for trending
    volatility_lookback_days: int = 20

    # Session times (in UTC)
    pre_market_start_hour: int = 8  # 4 AM ET
    regular_start_hour: int = 13  # 9:30 AM ET approximated
    regular_end_hour: int = 20  # 4 PM ET
    post_market_end_hour: int = 24  # 8 PM ET

    # Symbols to track for market internals
    volatility_index: str = "VIX"
    benchmark_symbol: str = "SPY"

    # Thresholds
    high_volatility_vix: float = 25.0
    low_volatility_vix: float = 15.0
    panic_vix: float = 35.0


class InitializerAgent(BaseAgent):
    """
    The Initializer Agent builds the Market State Object (MSO).

    It aggregates data from multiple sources to create a comprehensive
    view of current market conditions that guides all other agents.
    """

    def __init__(
        self,
        config: InitializerConfig,
        event_bus: EventBus,
        data_provider: Optional[Any] = None,
    ) -> None:
        super().__init__(config, event_bus)
        self.config: InitializerConfig = config
        self.data_provider = data_provider

        # Cache for computed values
        self._regime_cache: dict[str, tuple[datetime, Regime]] = {}
        self._volatility_cache: dict[str, tuple[datetime, Volatility]] = {}

    async def initialize(self) -> None:
        """Initialize the Initializer Agent."""
        self.logger.info("Initializing Initializer Agent")
        # In production, connect to data sources here
        self.logger.info("Initializer Agent ready")

    async def shutdown(self) -> None:
        """Shutdown the Initializer Agent."""
        self.logger.info("Shutting down Initializer Agent")

    async def process(self, mso: MarketStateObject, **kwargs: Any) -> MarketStateObject:
        """
        Build or update the Market State Object.

        Args:
            mso: The existing MSO to update (or a fresh one)
            **kwargs: Additional data (e.g., price_data, events)

        Returns:
            Updated MarketStateObject
        """
        now = datetime.utcnow()

        # Update timestamp
        mso.timestamp = now

        # Determine session
        mso.session = self._determine_session(now)

        # Update time context
        mso.day_of_week = now.weekday()
        mso.is_month_end = self._is_month_end(now)
        mso.is_quarter_end = self._is_quarter_end(now)
        mso.is_opex = self._is_options_expiration(now)

        # Determine global regime
        mso.regime = await self._determine_regime(kwargs.get("market_data"))

        # Determine global volatility
        mso.volatility = await self._determine_volatility(kwargs.get("vix_data"))

        # Determine liquidity
        mso.liquidity = self._determine_liquidity(mso)

        # Update instrument states
        if "instruments" in kwargs:
            for symbol, data in kwargs["instruments"].items():
                instrument_state = await self._build_instrument_state(symbol, data)
                mso.instruments[symbol] = instrument_state

        # Process macro events
        if "events" in kwargs:
            mso.macro_events = self._process_macro_events(kwargs["events"])
            mso.next_major_event = self._get_next_major_event(mso.macro_events)
            if mso.next_major_event:
                delta = mso.next_major_event.timestamp - now
                mso.hours_to_next_event = delta.total_seconds() / 3600

        # Determine allowed playbooks
        mso.allowed_playbooks = self._determine_playbooks(mso)

        # Generate summary
        mso.generate_summary()

        self.logger.info(f"MSO updated: {mso.summary}")

        return mso

    def _determine_session(self, now: datetime) -> Session:
        """Determine current market session."""
        hour = now.hour
        day_of_week = now.weekday()

        # Weekend
        if day_of_week >= 5:
            return Session.CLOSED

        # Check session times (simplified UTC approximation)
        if hour < self.config.pre_market_start_hour:
            return Session.OVERNIGHT
        elif hour < self.config.regular_start_hour:
            return Session.PRE_MARKET
        elif hour < self.config.regular_end_hour:
            return Session.REGULAR_HOURS
        elif hour < self.config.post_market_end_hour:
            return Session.POST_MARKET
        else:
            return Session.OVERNIGHT

    def _is_month_end(self, now: datetime) -> bool:
        """Check if current date is month end (last 3 days)."""
        next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
        last_day = next_month - timedelta(days=1)
        return (last_day - now).days <= 3

    def _is_quarter_end(self, now: datetime) -> bool:
        """Check if current date is quarter end."""
        return now.month in [3, 6, 9, 12] and self._is_month_end(now)

    def _is_options_expiration(self, now: datetime) -> bool:
        """Check if current date is options expiration (3rd Friday)."""
        # Simple approximation: third Friday
        if now.weekday() != 4:  # Not Friday
            return False
        day = now.day
        # Third Friday is between 15th and 21st
        return 15 <= day <= 21

    async def _determine_regime(self, market_data: Optional[dict] = None) -> Regime:
        """
        Determine market regime from price data.

        Uses multiple indicators:
        - ADX for trend strength
        - Hurst exponent for mean-reversion tendency
        - VIX for panic detection
        """
        if market_data is None:
            return Regime.CHOPPY  # Default when no data

        # Check for panic first (VIX spike)
        vix = market_data.get("vix")
        if vix and vix > self.config.panic_vix:
            return Regime.PANIC

        # Calculate trend metrics
        prices = market_data.get("prices", [])
        if len(prices) < self.config.regime_lookback_days:
            return Regime.CHOPPY

        # Simplified regime detection using price efficiency
        returns = np.diff(prices) / prices[:-1]
        cumulative_return = abs(prices[-1] - prices[0]) / prices[0]
        volatility = np.std(returns) * np.sqrt(len(returns))

        efficiency = cumulative_return / volatility if volatility > 0 else 0

        if efficiency > self.config.trending_threshold:
            return Regime.TRENDING
        elif efficiency < 0.2:
            return Regime.MEAN_REVERTING
        else:
            return Regime.CHOPPY

    async def _determine_volatility(self, vix_data: Optional[dict] = None) -> Volatility:
        """Determine volatility level from VIX or realized vol."""
        if vix_data is None:
            return Volatility.NORMAL

        vix = vix_data.get("level", 20)

        if vix >= self.config.high_volatility_vix:
            return Volatility.HIGH
        elif vix <= self.config.low_volatility_vix:
            return Volatility.LOW
        else:
            return Volatility.NORMAL

    def _determine_liquidity(self, mso: MarketStateObject) -> Liquidity:
        """Determine liquidity conditions."""
        # Event risk
        if mso.hours_to_next_event and mso.hours_to_next_event < 1:
            return Liquidity.EVENT_RISK

        # Outside regular hours
        if mso.session in [Session.PRE_MARKET, Session.POST_MARKET, Session.OVERNIGHT]:
            return Liquidity.THIN

        # Panic regime
        if mso.regime == Regime.PANIC:
            return Liquidity.EVENT_RISK

        return Liquidity.NORMAL

    async def _build_instrument_state(
        self, symbol: str, data: dict
    ) -> InstrumentState:
        """Build instrument state from market data."""
        state = InstrumentState(
            symbol=symbol,
            asset_class=data.get("asset_class", AssetClass.EQUITIES),
            last_price=data.get("last_price"),
            bid=data.get("bid"),
            ask=data.get("ask"),
            volume=data.get("volume"),
        )

        # Calculate trend bias
        if "prices" in data and len(data["prices"]) > 20:
            state.trend_bias = self._calculate_trend_bias(data["prices"])

        # Set key levels
        if "ohlc" in data:
            state.key_levels = self._calculate_key_levels(data["ohlc"])

        # Calculate ATR
        if "high" in data and "low" in data and "close" in data:
            state.atr = self._calculate_atr(
                data["high"], data["low"], data["close"]
            )
            if state.last_price and state.atr:
                state.atr_percent = (state.atr / state.last_price) * 100

        # Options-specific data
        if "iv_rank" in data:
            state.iv_rank = data["iv_rank"]
        if "iv_percentile" in data:
            state.iv_percentile = data["iv_percentile"]

        return state

    def _calculate_trend_bias(self, prices: list[float]) -> TrendBias:
        """Calculate trend bias from price history."""
        if len(prices) < 20:
            return TrendBias.RANGE

        # Simple trend detection using moving averages
        short_ma = np.mean(prices[-10:])
        long_ma = np.mean(prices[-20:])
        current = prices[-1]

        # Calculate momentum
        momentum = (current - prices[-20]) / prices[-20] * 100

        if momentum > 10 and current > short_ma > long_ma:
            return TrendBias.STRONG_UP
        elif momentum > 3 and current > long_ma:
            return TrendBias.WEAK_UP
        elif momentum < -10 and current < short_ma < long_ma:
            return TrendBias.STRONG_DOWN
        elif momentum < -3 and current < long_ma:
            return TrendBias.WEAK_DOWN
        elif momentum < -15:
            return TrendBias.CAPITULATION
        else:
            return TrendBias.RANGE

    def _calculate_key_levels(self, ohlc: dict) -> KeyLevels:
        """Calculate key price levels from OHLC data."""
        levels = KeyLevels()

        if "prior_day" in ohlc:
            pd = ohlc["prior_day"]
            levels.prior_day_high = pd.get("high")
            levels.prior_day_low = pd.get("low")
            levels.prior_day_close = pd.get("close")

        if "prior_week" in ohlc:
            pw = ohlc["prior_week"]
            levels.prior_week_high = pw.get("high")
            levels.prior_week_low = pw.get("low")

        if "session" in ohlc:
            sess = ohlc["session"]
            levels.session_open = sess.get("open")
            levels.session_high = sess.get("high")
            levels.session_low = sess.get("low")

        if "vwap" in ohlc:
            levels.vwap = ohlc["vwap"]

        if "volume_profile" in ohlc:
            vp = ohlc["volume_profile"]
            levels.poc = vp.get("poc")
            levels.value_area_high = vp.get("vah")
            levels.value_area_low = vp.get("val")

        return levels

    def _calculate_atr(
        self,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14,
    ) -> Optional[float]:
        """Calculate Average True Range."""
        if len(highs) < period + 1:
            return None

        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            true_ranges.append(tr)

        return np.mean(true_ranges[-period:])

    def _process_macro_events(self, events: list[dict]) -> list[MacroEvent]:
        """Process raw event data into MacroEvent objects."""
        macro_events = []
        for event in events:
            try:
                macro_events.append(
                    MacroEvent(
                        name=event["name"],
                        timestamp=event["timestamp"],
                        impact=event.get("impact", "medium"),
                        affected_assets=event.get("affected_assets", []),
                        description=event.get("description"),
                    )
                )
            except Exception as e:
                self.logger.warning(f"Failed to parse event: {e}")

        return sorted(macro_events, key=lambda x: x.timestamp)

    def _get_next_major_event(
        self, events: list[MacroEvent]
    ) -> Optional[MacroEvent]:
        """Get the next high-impact event."""
        now = datetime.utcnow()
        for event in events:
            if event.timestamp > now and event.impact == "high":
                return event
        return None

    def _determine_playbooks(self, mso: MarketStateObject) -> AllowedPlaybooks:
        """Determine which trading playbooks are allowed."""
        playbooks = AllowedPlaybooks()

        # Regime-based restrictions
        if mso.regime == Regime.PANIC:
            playbooks.trend_following = False
            playbooks.mean_reversion = False
            playbooks.momentum = False
            playbooks.scalping = False
            playbooks.max_position_size_multiplier = 0.25
            playbooks.max_new_positions = 0
            playbooks.avoid_new_swing = True
            playbooks.avoid_new_overnight = True

        elif mso.regime == Regime.CHOPPY:
            playbooks.trend_following = False
            playbooks.max_position_size_multiplier = 0.75

        elif mso.regime == Regime.MEAN_REVERTING:
            playbooks.trend_following = False
            playbooks.momentum = False

        # Volatility-based restrictions
        if mso.volatility == Volatility.HIGH:
            playbooks.mean_reversion = False
            playbooks.max_position_size_multiplier *= 0.5
            playbooks.avoid_new_overnight = True

        # Liquidity-based restrictions
        if mso.liquidity == Liquidity.THIN:
            playbooks.scalping = False
            playbooks.max_position_size_multiplier *= 0.5

        if mso.liquidity == Liquidity.EVENT_RISK:
            playbooks.max_new_positions = 0
            playbooks.avoid_new_swing = True
            playbooks.avoid_new_overnight = True

        # Session-based restrictions
        if mso.session != Session.REGULAR_HOURS:
            playbooks.scalping = False
            playbooks.max_position_size_multiplier *= 0.5

        # Event-based restrictions
        if mso.hours_to_next_event and mso.hours_to_next_event < 2:
            playbooks.avoid_new_swing = True
            playbooks.max_new_positions = min(playbooks.max_new_positions, 3)

        return playbooks
