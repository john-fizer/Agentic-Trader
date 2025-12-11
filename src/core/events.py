"""
Event system for the D.A.T.A. trading agent.

Provides event definitions and an event bus for communication between agents.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from collections import defaultdict

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events in the trading system."""

    # Market data events
    NEW_BAR = "new_bar"
    TICK = "tick"
    QUOTE_UPDATE = "quote_update"

    # Trading events
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"

    # Risk events
    RISK_LIMIT_BREACH = "risk_limit_breach"
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_BREACH = "drawdown_breach"
    SLIPPAGE_ANOMALY = "slippage_anomaly"

    # System events
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    KILL_SWITCH = "kill_switch"
    HEARTBEAT = "heartbeat"

    # Agent events
    MSO_UPDATED = "mso_updated"
    STRATEGY_SIGNAL = "strategy_signal"
    TRADE_APPROVED = "trade_approved"
    TRADE_REJECTED = "trade_rejected"

    # Macro events
    MACRO_EVENT = "macro_event"
    SESSION_CHANGE = "session_change"

    # ML events
    MODEL_RETRAIN_TRIGGERED = "model_retrain_triggered"
    MODEL_UPDATED = "model_updated"


class Event(BaseModel):
    """Base event class for all system events."""

    event_type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = "system"  # Which agent/component generated this event
    data: dict[str, Any] = Field(default_factory=dict)

    # Optional correlation for tracking related events
    correlation_id: Optional[str] = None

    class Config:
        use_enum_values = True


class NewBarEvent(Event):
    """Event fired when a new bar/candle is complete."""

    event_type: EventType = EventType.NEW_BAR
    symbol: str = ""
    timeframe: str = ""  # e.g., "1m", "5m", "1h", "1d"
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0


class OrderEvent(Event):
    """Event related to order lifecycle."""

    order_id: str = ""
    symbol: str = ""
    side: str = ""  # buy, sell
    quantity: float = 0.0
    price: Optional[float] = None
    filled_price: Optional[float] = None
    filled_quantity: float = 0.0
    slippage: Optional[float] = None


class RiskEvent(Event):
    """Event related to risk management."""

    severity: str = "warning"  # warning, breach, critical
    metric: str = ""  # drawdown, exposure, concentration
    current_value: float = 0.0
    threshold: float = 0.0
    message: str = ""


EventHandler = Callable[[Event], None]


class EventBus:
    """
    Simple event bus for pub/sub communication between agents.

    In production, this would be backed by Redis Pub/Sub or Kafka.
    This implementation provides an in-memory version for local development.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._all_handlers: list[EventHandler] = []
        self._event_history: list[Event] = []
        self._max_history: int = 10000

    def subscribe(
        self, event_type: EventType | None, handler: EventHandler
    ) -> None:
        """
        Subscribe to events.

        Args:
            event_type: The event type to subscribe to. If None, subscribe to all events.
            handler: The callback function to invoke when event is published.
        """
        if event_type is None:
            self._all_handlers.append(handler)
        else:
            self._handlers[event_type].append(handler)

    def unsubscribe(
        self, event_type: EventType | None, handler: EventHandler
    ) -> None:
        """Unsubscribe from events."""
        if event_type is None:
            if handler in self._all_handlers:
                self._all_handlers.remove(handler)
        else:
            if handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribed handlers.

        Args:
            event: The event to publish.
        """
        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        # Notify specific handlers
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as e:
                # Log but don't propagate to avoid breaking the event chain
                print(f"Error in event handler: {e}")

        # Notify global handlers
        for handler in self._all_handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"Error in global event handler: {e}")

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get recent events from history."""
        if event_type is None:
            return self._event_history[-limit:]

        return [e for e in self._event_history if e.event_type == event_type][-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._event_history.clear()
