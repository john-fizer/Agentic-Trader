"""Tests for Market State Object (MSO)."""

import pytest
from datetime import datetime, timedelta

from src.core.market_state import (
    MarketStateObject,
    Regime,
    Volatility,
    Liquidity,
    Session,
    TrendBias,
    AssetClass,
    Timeframe,
    InstrumentState,
    KeyLevels,
    MacroEvent,
    AllowedPlaybooks,
)


class TestMarketStateObject:
    """Tests for MarketStateObject."""

    def test_create_default_mso(self):
        """Test creating MSO with defaults."""
        mso = MarketStateObject()

        assert mso.regime == Regime.CHOPPY
        assert mso.volatility == Volatility.NORMAL
        assert mso.liquidity == Liquidity.NORMAL
        assert mso.session == Session.REGULAR_HOURS
        assert len(mso.instruments) == 0
        assert len(mso.macro_events) == 0

    def test_is_high_risk_panic(self):
        """Test high risk detection in panic regime."""
        mso = MarketStateObject(regime=Regime.PANIC)
        assert mso.is_high_risk() is True

    def test_is_high_risk_high_vol(self):
        """Test high risk detection with high volatility."""
        mso = MarketStateObject(volatility=Volatility.HIGH)
        assert mso.is_high_risk() is True

    def test_is_high_risk_event_risk(self):
        """Test high risk detection with event risk."""
        mso = MarketStateObject(liquidity=Liquidity.EVENT_RISK)
        assert mso.is_high_risk() is True

    def test_is_high_risk_near_event(self):
        """Test high risk detection near macro event."""
        mso = MarketStateObject(hours_to_next_event=1.5)
        assert mso.is_high_risk() is True

    def test_is_not_high_risk_normal(self):
        """Test normal conditions are not high risk."""
        mso = MarketStateObject()
        assert mso.is_high_risk() is False

    def test_can_open_position_panic(self):
        """Test position opening blocked in panic."""
        mso = MarketStateObject(regime=Regime.PANIC)
        can_open, reason = mso.can_open_new_position("SPY", Timeframe.INTRADAY)

        assert can_open is False
        assert "panic" in reason.lower()

    def test_can_open_position_event_risk(self):
        """Test position opening blocked during event risk."""
        mso = MarketStateObject(liquidity=Liquidity.EVENT_RISK)
        can_open, reason = mso.can_open_new_position("SPY", Timeframe.INTRADAY)

        assert can_open is False
        assert "event" in reason.lower()

    def test_can_open_position_swing_restricted(self):
        """Test swing positions restricted."""
        mso = MarketStateObject()
        mso.allowed_playbooks.avoid_new_swing = True

        can_open, reason = mso.can_open_new_position("SPY", Timeframe.SWING)

        assert can_open is False
        assert "swing" in reason.lower()

    def test_can_open_position_normal(self):
        """Test normal position opening allowed."""
        mso = MarketStateObject()
        can_open, reason = mso.can_open_new_position("SPY", Timeframe.INTRADAY)

        assert can_open is True
        assert reason == "OK"

    def test_get_instrument(self):
        """Test getting instrument state."""
        mso = MarketStateObject()
        instrument = InstrumentState(
            symbol="SPY",
            asset_class=AssetClass.EQUITIES,
            last_price=450.0,
        )
        mso.instruments["SPY"] = instrument

        result = mso.get_instrument("SPY")
        assert result is not None
        assert result.symbol == "SPY"
        assert result.last_price == 450.0

        # Test non-existent
        assert mso.get_instrument("UNKNOWN") is None

    def test_generate_summary(self):
        """Test summary generation."""
        mso = MarketStateObject(
            regime=Regime.TRENDING,
            volatility=Volatility.HIGH,
            liquidity=Liquidity.NORMAL,
            session=Session.REGULAR_HOURS,
        )

        summary = mso.generate_summary()

        assert "trending" in summary.lower()
        assert "high" in summary.lower()
        assert "regular" in summary.lower()


class TestInstrumentState:
    """Tests for InstrumentState."""

    def test_create_instrument(self):
        """Test creating instrument state."""
        instrument = InstrumentState(
            symbol="AAPL",
            asset_class=AssetClass.EQUITIES,
            trend_bias=TrendBias.STRONG_UP,
            last_price=175.0,
            atr=2.5,
        )

        assert instrument.symbol == "AAPL"
        assert instrument.trend_bias == TrendBias.STRONG_UP
        assert instrument.is_tradeable is True

    def test_instrument_restricted(self):
        """Test restricted instrument."""
        instrument = InstrumentState(
            symbol="HALT",
            asset_class=AssetClass.EQUITIES,
            is_tradeable=False,
            restricted_reason="Trading halted",
        )

        assert instrument.is_tradeable is False
        assert instrument.restricted_reason == "Trading halted"


class TestKeyLevels:
    """Tests for KeyLevels."""

    def test_create_key_levels(self):
        """Test creating key levels."""
        levels = KeyLevels(
            prior_day_high=452.0,
            prior_day_low=448.0,
            prior_day_close=450.0,
            vwap=449.5,
        )

        assert levels.prior_day_high == 452.0
        assert levels.prior_day_low == 448.0
        assert levels.vwap == 449.5


class TestMacroEvent:
    """Tests for MacroEvent."""

    def test_create_macro_event(self):
        """Test creating macro event."""
        event = MacroEvent(
            name="FOMC Decision",
            timestamp=datetime.utcnow() + timedelta(hours=2),
            impact="high",
            affected_assets=["SPY", "QQQ", "TLT"],
        )

        assert event.name == "FOMC Decision"
        assert event.impact == "high"
        assert len(event.affected_assets) == 3


class TestAllowedPlaybooks:
    """Tests for AllowedPlaybooks."""

    def test_default_playbooks(self):
        """Test default playbook settings."""
        playbooks = AllowedPlaybooks()

        assert playbooks.trend_following is True
        assert playbooks.mean_reversion is True
        assert playbooks.max_position_size_multiplier == 1.0
        assert playbooks.avoid_new_swing is False

    def test_restricted_playbooks(self):
        """Test restricted playbook settings."""
        playbooks = AllowedPlaybooks(
            trend_following=False,
            mean_reversion=False,
            max_position_size_multiplier=0.5,
            avoid_new_swing=True,
            max_new_positions=0,
        )

        assert playbooks.trend_following is False
        assert playbooks.max_new_positions == 0
