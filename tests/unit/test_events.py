"""Tests for the event system."""

import pytest
from datetime import datetime

from src.core.events import (
    Event,
    EventType,
    EventBus,
    NewBarEvent,
    OrderEvent,
    RiskEvent,
)


class TestEvent:
    """Tests for Event class."""

    def test_create_event(self):
        """Test creating a basic event."""
        event = Event(
            event_type=EventType.NEW_BAR,
            source="test",
            data={"symbol": "SPY"},
        )

        assert event.event_type == EventType.NEW_BAR
        assert event.source == "test"
        assert event.data["symbol"] == "SPY"
        assert event.timestamp is not None

    def test_new_bar_event(self):
        """Test NewBarEvent."""
        event = NewBarEvent(
            symbol="SPY",
            timeframe="5m",
            open=450.0,
            high=451.0,
            low=449.0,
            close=450.5,
            volume=1000000.0,
        )

        assert event.event_type == EventType.NEW_BAR
        assert event.symbol == "SPY"
        assert event.close == 450.5

    def test_order_event(self):
        """Test OrderEvent."""
        event = OrderEvent(
            event_type=EventType.ORDER_FILLED,
            order_id="order-123",
            symbol="AAPL",
            side="buy",
            quantity=100.0,
            filled_price=175.0,
            slippage=0.05,
        )

        assert event.event_type == EventType.ORDER_FILLED
        assert event.order_id == "order-123"
        assert event.slippage == 0.05

    def test_risk_event(self):
        """Test RiskEvent."""
        event = RiskEvent(
            event_type=EventType.RISK_LIMIT_BREACH,
            severity="warning",
            metric="drawdown",
            current_value=3.5,
            threshold=3.0,
            message="Daily drawdown limit approaching",
        )

        assert event.severity == "warning"
        assert event.metric == "drawdown"
        assert event.current_value > event.threshold


class TestEventBus:
    """Tests for EventBus."""

    def test_subscribe_and_publish(self):
        """Test basic subscribe and publish."""
        bus = EventBus()
        received_events = []

        def handler(event: Event):
            received_events.append(event)

        bus.subscribe(EventType.NEW_BAR, handler)

        event = Event(event_type=EventType.NEW_BAR)
        bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].event_type == EventType.NEW_BAR

    def test_subscribe_all_events(self):
        """Test subscribing to all events."""
        bus = EventBus()
        received_events = []

        def handler(event: Event):
            received_events.append(event)

        bus.subscribe(None, handler)  # Subscribe to all

        bus.publish(Event(event_type=EventType.NEW_BAR))
        bus.publish(Event(event_type=EventType.ORDER_FILLED))

        assert len(received_events) == 2

    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        bus = EventBus()
        received_events = []

        def handler(event: Event):
            received_events.append(event)

        bus.subscribe(EventType.NEW_BAR, handler)
        bus.publish(Event(event_type=EventType.NEW_BAR))

        bus.unsubscribe(EventType.NEW_BAR, handler)
        bus.publish(Event(event_type=EventType.NEW_BAR))

        assert len(received_events) == 1

    def test_event_history(self):
        """Test event history tracking."""
        bus = EventBus()

        for i in range(5):
            bus.publish(Event(event_type=EventType.NEW_BAR, data={"i": i}))

        history = bus.get_history(EventType.NEW_BAR, limit=3)
        assert len(history) == 3
        assert history[-1].data["i"] == 4  # Most recent

    def test_handler_error_isolation(self):
        """Test that handler errors don't break the event chain."""
        bus = EventBus()
        received_events = []

        def bad_handler(event: Event):
            raise ValueError("Handler error")

        def good_handler(event: Event):
            received_events.append(event)

        bus.subscribe(EventType.NEW_BAR, bad_handler)
        bus.subscribe(EventType.NEW_BAR, good_handler)

        # Should not raise, and good_handler should still receive event
        bus.publish(Event(event_type=EventType.NEW_BAR))

        assert len(received_events) == 1

    def test_clear_history(self):
        """Test clearing event history."""
        bus = EventBus()

        bus.publish(Event(event_type=EventType.NEW_BAR))
        assert len(bus.get_history()) > 0

        bus.clear_history()
        assert len(bus.get_history()) == 0
