"""
Market State Object (MSO) - The shared context for all agents.

The MSO is the foundational data structure that captures the current market environment
and is passed to all agents to ensure coherent decision-making.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Regime(str, Enum):
    """Market regime classification."""

    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    CHOPPY = "choppy"
    PANIC = "panic"


class Volatility(str, Enum):
    """Volatility classification."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class Liquidity(str, Enum):
    """Liquidity classification."""

    NORMAL = "normal"
    THIN = "thin"
    EVENT_RISK = "event_risk"


class Session(str, Enum):
    """Market session classification."""

    PRE_MARKET = "pre_market"
    REGULAR_HOURS = "regular_hours"
    POST_MARKET = "post_market"
    OVERNIGHT = "overnight"  # For 24/7 markets like crypto
    CLOSED = "closed"


class TrendBias(str, Enum):
    """Trend bias classification for instruments."""

    STRONG_UP = "strong_up"
    WEAK_UP = "weak_up"
    RANGE = "range"
    WEAK_DOWN = "weak_down"
    STRONG_DOWN = "strong_down"
    DISTRIBUTION = "distribution"
    ACCUMULATION = "accumulation"
    CAPITULATION = "capitulation"


class AssetClass(str, Enum):
    """Asset class classification."""

    EQUITIES = "equities"
    OPTIONS = "options"
    FUTURES = "futures"
    CRYPTO = "crypto"
    FOREX = "forex"


class Timeframe(str, Enum):
    """Timeframe classification for strategies."""

    SCALP = "scalp"  # 1-15 minutes
    INTRADAY = "intraday"  # 15 min - 4 hours
    SWING = "swing"  # 4 hours - days
    POSITION = "position"  # Days - weeks


class KeyLevels(BaseModel):
    """Key price levels for an instrument."""

    prior_day_high: Optional[float] = None
    prior_day_low: Optional[float] = None
    prior_day_close: Optional[float] = None
    prior_week_high: Optional[float] = None
    prior_week_low: Optional[float] = None
    session_open: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    vwap: Optional[float] = None
    poc: Optional[float] = None  # Point of Control (volume profile)
    value_area_high: Optional[float] = None
    value_area_low: Optional[float] = None
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)


class InstrumentState(BaseModel):
    """State information for a single instrument."""

    symbol: str
    asset_class: AssetClass
    trend_bias: TrendBias = TrendBias.RANGE
    volatility: Volatility = Volatility.NORMAL
    liquidity: Liquidity = Liquidity.NORMAL
    key_levels: KeyLevels = Field(default_factory=KeyLevels)

    # Current price data
    last_price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[float] = None

    # Derived metrics
    atr: Optional[float] = None  # Average True Range
    atr_percent: Optional[float] = None  # ATR as percentage of price
    iv_rank: Optional[float] = None  # Implied volatility rank (options)
    iv_percentile: Optional[float] = None  # IV percentile

    # Flags
    is_tradeable: bool = True
    restricted_reason: Optional[str] = None

    class Config:
        use_enum_values = True


class MacroEvent(BaseModel):
    """Upcoming macro event that may affect trading."""

    name: str
    timestamp: datetime
    impact: str = "medium"  # low, medium, high
    affected_assets: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class AllowedPlaybooks(BaseModel):
    """Playbooks/strategies allowed in current market conditions."""

    trend_following: bool = True
    mean_reversion: bool = True
    volatility: bool = True
    momentum: bool = True
    spreads: bool = True
    scalping: bool = True

    # Restrictions
    max_position_size_multiplier: float = 1.0  # Scale down in risky conditions
    max_new_positions: int = 10
    avoid_new_swing: bool = False
    avoid_new_overnight: bool = False


class MarketStateObject(BaseModel):
    """
    Market State Object (MSO) - The shared context passed to all agents.

    This is the single source of truth for current market conditions,
    ensuring all agents make decisions based on consistent information.
    """

    # Timestamp
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    as_of_bar: Optional[datetime] = None  # The bar/candle this state represents

    # Global market conditions
    regime: Regime = Regime.CHOPPY
    volatility: Volatility = Volatility.NORMAL
    liquidity: Liquidity = Liquidity.NORMAL

    # Time context
    session: Session = Session.REGULAR_HOURS
    day_of_week: int = 0  # 0 = Monday
    is_month_end: bool = False
    is_quarter_end: bool = False
    is_opex: bool = False  # Options expiration

    # Per-instrument states
    instruments: dict[str, InstrumentState] = Field(default_factory=dict)

    # Upcoming events
    macro_events: list[MacroEvent] = Field(default_factory=list)
    next_major_event: Optional[MacroEvent] = None
    hours_to_next_event: Optional[float] = None

    # Allowed playbooks based on current conditions
    allowed_playbooks: AllowedPlaybooks = Field(default_factory=AllowedPlaybooks)

    # Market internals (breadth, sentiment)
    market_breadth: Optional[float] = None  # % of stocks above 50 MA
    put_call_ratio: Optional[float] = None
    vix_level: Optional[float] = None
    vix_term_structure: Optional[str] = None  # contango, backwardation, flat

    # Human-readable summary for monitoring
    summary: str = ""

    class Config:
        use_enum_values = True

    def get_instrument(self, symbol: str) -> Optional[InstrumentState]:
        """Get instrument state by symbol."""
        return self.instruments.get(symbol)

    def is_high_risk(self) -> bool:
        """Check if current conditions are high risk."""
        return (
            self.regime == Regime.PANIC
            or self.volatility == Volatility.HIGH
            or self.liquidity == Liquidity.EVENT_RISK
            or (self.hours_to_next_event is not None and self.hours_to_next_event < 2)
        )

    def can_open_new_position(self, symbol: str, timeframe: Timeframe) -> tuple[bool, str]:
        """Check if a new position can be opened for given instrument and timeframe."""
        # Check global restrictions
        if self.regime == Regime.PANIC:
            return False, "Market in panic mode - no new positions"

        if self.liquidity == Liquidity.EVENT_RISK:
            return False, "Event risk - no new positions"

        # Check timeframe restrictions
        if timeframe == Timeframe.SWING and self.allowed_playbooks.avoid_new_swing:
            return False, "Swing positions restricted in current conditions"

        if timeframe == Timeframe.POSITION and self.allowed_playbooks.avoid_new_overnight:
            return False, "Overnight positions restricted"

        # Check instrument-specific restrictions
        instrument = self.get_instrument(symbol)
        if instrument:
            if not instrument.is_tradeable:
                return False, f"Instrument restricted: {instrument.restricted_reason}"

        return True, "OK"

    def generate_summary(self) -> str:
        """Generate human-readable summary of market state."""
        parts = []

        # Regime and volatility
        parts.append(f"Regime: {self.regime.value}")
        parts.append(f"Vol: {self.volatility.value}")
        parts.append(f"Liq: {self.liquidity.value}")

        # Session
        parts.append(f"Session: {self.session.value}")

        # Risk level
        if self.is_high_risk():
            parts.append("⚠️ HIGH RISK")

        # Upcoming events
        if self.next_major_event and self.hours_to_next_event:
            parts.append(
                f"Next event: {self.next_major_event.name} in {self.hours_to_next_event:.1f}h"
            )

        # Playbook restrictions
        restrictions = []
        if not self.allowed_playbooks.trend_following:
            restrictions.append("no trend")
        if not self.allowed_playbooks.mean_reversion:
            restrictions.append("no MR")
        if self.allowed_playbooks.avoid_new_swing:
            restrictions.append("no new swing")

        if restrictions:
            parts.append(f"Restricted: {', '.join(restrictions)}")

        self.summary = " | ".join(parts)
        return self.summary
