"""Tests for trade-related models."""

import pytest
from datetime import datetime, timedelta

from src.core.trade import (
    CandidateTrade,
    Order,
    Position,
    PortfolioSnapshot,
    OrderType,
    OrderStatus,
    Side,
    PositionSide,
    TradeTimeframe,
)


class TestCandidateTrade:
    """Tests for CandidateTrade."""

    def test_create_candidate_trade(self):
        """Test creating a candidate trade."""
        trade = CandidateTrade(
            symbol="AAPL",
            side=Side.BUY,
            suggested_size=100.0,
            entry_price=175.0,
            stop_loss=170.0,
            take_profit=185.0,
            strategy_name="trend_following",
            signal_strength=0.8,
        )

        assert trade.symbol == "AAPL"
        assert trade.side == Side.BUY
        assert trade.suggested_size == 100.0
        assert trade.stop_loss == 170.0

    def test_calculate_risk_metrics_long(self):
        """Test risk calculation for long trade."""
        trade = CandidateTrade(
            symbol="AAPL",
            side=Side.BUY,
            suggested_size=100.0,
            entry_price=175.0,
            stop_loss=170.0,
            take_profit=185.0,
            strategy_name="test",
        )

        trade.calculate_risk_metrics(account_equity=100000.0)

        assert trade.risk_amount == 500.0  # (175 - 170) * 100
        assert trade.risk_percent == 0.5  # 500 / 100000 * 100
        assert trade.reward_risk_ratio == 2.0  # (185 - 175) / (175 - 170)

    def test_calculate_risk_metrics_short(self):
        """Test risk calculation for short trade."""
        trade = CandidateTrade(
            symbol="AAPL",
            side=Side.SELL,
            suggested_size=100.0,
            entry_price=175.0,
            stop_loss=180.0,
            take_profit=165.0,
            strategy_name="test",
        )

        trade.calculate_risk_metrics(account_equity=100000.0)

        assert trade.risk_amount == 500.0  # (180 - 175) * 100
        assert trade.reward_risk_ratio == 2.0  # (175 - 165) / (180 - 175)


class TestOrder:
    """Tests for Order."""

    def test_create_order(self):
        """Test creating an order."""
        order = Order(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100.0,
            order_type=OrderType.LIMIT,
            limit_price=175.0,
        )

        assert order.symbol == "AAPL"
        assert order.status == OrderStatus.PENDING
        assert order.order_type == OrderType.LIMIT

    def test_order_is_complete(self):
        """Test order completion status."""
        order = Order(symbol="AAPL", side=Side.BUY, quantity=100.0)

        assert order.is_complete is False

        order.status = OrderStatus.FILLED
        assert order.is_complete is True

        order.status = OrderStatus.CANCELLED
        assert order.is_complete is True

    def test_remaining_quantity(self):
        """Test remaining quantity calculation."""
        order = Order(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100.0,
            filled_quantity=30.0,
        )

        assert order.remaining_quantity == 70.0

    def test_calculate_slippage_buy(self):
        """Test slippage calculation for buy."""
        order = Order(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100.0,
            average_fill_price=175.50,
        )

        order.calculate_slippage(expected_price=175.0)
        assert order.slippage == 0.50

    def test_calculate_slippage_sell(self):
        """Test slippage calculation for sell."""
        order = Order(
            symbol="AAPL",
            side=Side.SELL,
            quantity=100.0,
            average_fill_price=174.50,
        )

        order.calculate_slippage(expected_price=175.0)
        assert order.slippage == 0.50


class TestPosition:
    """Tests for Position."""

    def test_create_position(self):
        """Test creating a position."""
        position = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            average_entry_price=175.0,
            stop_loss=170.0,
            take_profit=185.0,
        )

        assert position.symbol == "AAPL"
        assert position.side == PositionSide.LONG
        assert position.is_open is True

    def test_position_market_value(self):
        """Test market value calculation."""
        position = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            average_entry_price=175.0,
            current_price=180.0,
        )

        assert position.market_value == 18000.0
        assert position.cost_basis == 17500.0

    def test_update_price_long(self):
        """Test price update for long position."""
        position = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            average_entry_price=175.0,
        )

        position.update_price(180.0)

        assert position.unrealized_pnl == 500.0
        assert position.max_favorable_excursion == 500.0

        position.update_price(173.0)
        assert position.unrealized_pnl == -200.0
        assert position.max_adverse_excursion == -200.0

    def test_update_price_short(self):
        """Test price update for short position."""
        position = Position(
            symbol="AAPL",
            side=PositionSide.SHORT,
            quantity=100.0,
            average_entry_price=175.0,
        )

        position.update_price(170.0)

        assert position.unrealized_pnl == 500.0

    def test_should_stop_out_long(self):
        """Test stop loss trigger for long."""
        position = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            average_entry_price=175.0,
            stop_loss=170.0,
            current_price=171.0,
        )

        assert position.should_stop_out() is False

        position.current_price = 169.0
        assert position.should_stop_out() is True

    def test_should_take_profit_long(self):
        """Test take profit trigger for long."""
        position = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            average_entry_price=175.0,
            take_profit=185.0,
            current_price=184.0,
        )

        assert position.should_take_profit() is False

        position.current_price = 186.0
        assert position.should_take_profit() is True


class TestPortfolioSnapshot:
    """Tests for PortfolioSnapshot."""

    def test_create_snapshot(self):
        """Test creating portfolio snapshot."""
        snapshot = PortfolioSnapshot(
            total_equity=100000.0,
            cash=50000.0,
            total_exposure=50000.0,
        )

        assert snapshot.total_equity == 100000.0
        assert snapshot.cash == 50000.0

    def test_exposure_calculations(self):
        """Test exposure calculations."""
        long_position = Position(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            average_entry_price=175.0,
            current_price=180.0,
        )

        short_position = Position(
            symbol="TSLA",
            side=PositionSide.SHORT,
            quantity=50.0,
            average_entry_price=200.0,
            current_price=195.0,
        )

        snapshot = PortfolioSnapshot(
            total_equity=100000.0,
            cash=70000.0,
            positions=[long_position, short_position],
        )

        assert snapshot.num_positions == 2
        assert snapshot.long_exposure == 18000.0  # 100 * 180
        assert snapshot.short_exposure == 9750.0  # 50 * 195
