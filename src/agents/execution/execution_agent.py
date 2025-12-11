"""
Execution Agent - Routes and manages orders.

The Execution Agent is responsible for:
- Converting approved trades into actual orders
- Deciding order types (market, limit, stop, algo)
- Routing orders to appropriate brokers/exchanges
- Managing partial fills, re-quotes, and cancellations
- Tracking fill prices, slippage, and latency
"""

from datetime import datetime
from typing import Any, Optional
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field
from loguru import logger

from src.agents.base import AgentConfig, BaseAgent
from src.core.events import Event, EventBus, EventType, OrderEvent
from src.core.market_state import AssetClass, MarketStateObject, Session
from src.core.trade import (
    CandidateTrade,
    Order,
    OrderStatus,
    OrderType,
    Side,
)


class BrokerConfig(BaseModel):
    """Configuration for a broker connection."""

    name: str
    broker_type: str  # alpaca, ib, ccxt, etc.
    enabled: bool = True
    paper_trading: bool = True
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    base_url: Optional[str] = None

    # Asset classes this broker handles
    asset_classes: list[AssetClass] = Field(
        default_factory=lambda: [AssetClass.EQUITIES]
    )

    # Rate limits
    max_orders_per_second: int = 10
    max_orders_per_minute: int = 60


class ExecutionAgentConfig(AgentConfig):
    """Configuration for the Execution Agent."""

    name: str = "execution"

    # Broker configurations
    brokers: list[BrokerConfig] = Field(default_factory=list)

    # Order defaults
    default_order_type: OrderType = OrderType.LIMIT
    limit_offset_percent: float = 0.1  # Offset for limit orders
    use_market_during_volatility: bool = True

    # Slippage tolerance
    max_slippage_percent: float = 0.5
    cancel_on_excess_slippage: bool = True

    # Timing
    order_timeout_seconds: int = 60
    retry_on_reject: bool = True
    max_retries: int = 3


class BrokerAdapter(ABC):
    """Abstract base class for broker adapters."""

    def __init__(self, config: BrokerConfig) -> None:
        self.config = config
        self.logger = logger.bind(broker=config.name)

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the broker."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """Submit an order to the broker."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status."""
        pass

    @abstractmethod
    async def get_positions(self) -> list[dict]:
        """Get current positions."""
        pass

    @abstractmethod
    async def get_account(self) -> dict:
        """Get account information."""
        pass


class SimulatedBroker(BrokerAdapter):
    """Simulated broker for paper trading and testing."""

    def __init__(self, config: BrokerConfig) -> None:
        super().__init__(config)
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, dict] = {}
        self._connected = False

    async def connect(self) -> bool:
        self._connected = True
        self.logger.info("Simulated broker connected")
        return True

    async def disconnect(self) -> None:
        self._connected = False
        self.logger.info("Simulated broker disconnected")

    async def submit_order(self, order: Order) -> Order:
        """Simulate order submission and immediate fill."""
        order.status = OrderStatus.SUBMITTED
        order.submitted_at = datetime.utcnow()
        order.broker_order_id = f"SIM-{order.id[:8]}"

        self._orders[order.id] = order

        # Simulate immediate fill for market orders
        if order.order_type == OrderType.MARKET:
            order = await self._simulate_fill(order)

        return order

    async def _simulate_fill(self, order: Order) -> Order:
        """Simulate order fill with small slippage."""
        import random

        base_price = order.limit_price or 100.0  # Default price for simulation

        # Add small random slippage
        slippage_pct = random.uniform(-0.1, 0.2)  # Slight adverse slippage bias
        slippage = base_price * (slippage_pct / 100)

        if order.side == Side.BUY:
            fill_price = base_price + slippage
        else:
            fill_price = base_price - slippage

        order.status = OrderStatus.FILLED
        order.filled_at = datetime.utcnow()
        order.filled_quantity = order.quantity
        order.average_fill_price = fill_price
        order.slippage = slippage

        self._orders[order.id] = order

        return order

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
                order.status = OrderStatus.CANCELLED
                order.cancelled_at = datetime.utcnow()
                return True
        return False

    async def get_order_status(self, order_id: str) -> Order:
        return self._orders.get(order_id)

    async def get_positions(self) -> list[dict]:
        return list(self._positions.values())

    async def get_account(self) -> dict:
        return {
            "equity": 100000.0,
            "cash": 100000.0,
            "buying_power": 200000.0,
        }


class ExecutionAgent(BaseAgent):
    """
    The Execution Agent converts approved trades into orders and manages execution.

    It handles broker connectivity, order routing, and execution quality tracking.
    """

    def __init__(
        self,
        config: ExecutionAgentConfig,
        event_bus: EventBus,
    ) -> None:
        super().__init__(config, event_bus)
        self.config: ExecutionAgentConfig = config

        # Broker adapters
        self._brokers: dict[str, BrokerAdapter] = {}

        # Order tracking
        self._pending_orders: dict[str, Order] = {}
        self._completed_orders: list[Order] = []

        # Execution metrics
        self._total_slippage: float = 0.0
        self._order_count: int = 0
        self._fill_rate: float = 1.0

    async def initialize(self) -> None:
        """Initialize the Execution Agent."""
        self.logger.info("Initializing Execution Agent")

        # Initialize broker adapters
        for broker_config in self.config.brokers:
            if broker_config.enabled:
                adapter = self._create_broker_adapter(broker_config)
                if adapter:
                    connected = await adapter.connect()
                    if connected:
                        self._brokers[broker_config.name] = adapter

        # Add simulated broker if no brokers configured
        if not self._brokers:
            self.logger.info("No brokers configured, using simulated broker")
            sim_config = BrokerConfig(
                name="simulated",
                broker_type="simulated",
                paper_trading=True,
            )
            sim_broker = SimulatedBroker(sim_config)
            await sim_broker.connect()
            self._brokers["simulated"] = sim_broker

        self.logger.info(
            f"Execution Agent ready with {len(self._brokers)} broker(s)"
        )

    async def shutdown(self) -> None:
        """Shutdown the Execution Agent."""
        self.logger.info("Shutting down Execution Agent")

        # Cancel pending orders
        for order_id, order in self._pending_orders.items():
            try:
                broker = self._get_broker_for_order(order)
                if broker:
                    await broker.cancel_order(order_id)
            except Exception as e:
                self.logger.error(f"Error cancelling order {order_id}: {e}")

        # Disconnect brokers
        for name, broker in self._brokers.items():
            try:
                await broker.disconnect()
            except Exception as e:
                self.logger.error(f"Error disconnecting broker {name}: {e}")

    async def process(
        self, mso: MarketStateObject, **kwargs: Any
    ) -> list[Order]:
        """
        Execute approved trades.

        Args:
            mso: Current Market State Object
            trades: List of approved trades to execute

        Returns:
            List of submitted orders
        """
        trades: list[CandidateTrade] = kwargs.get("trades", [])

        if not trades:
            return []

        orders: list[Order] = []

        for trade in trades:
            try:
                # Create order from trade
                order = self._create_order(trade, mso)

                # Route to appropriate broker
                broker = self._get_broker_for_trade(trade)
                if not broker:
                    self.logger.error(f"No broker available for {trade.symbol}")
                    continue

                # Submit order
                submitted_order = await broker.submit_order(order)
                orders.append(submitted_order)

                # Track order
                if submitted_order.status not in [
                    OrderStatus.FILLED,
                    OrderStatus.CANCELLED,
                    OrderStatus.REJECTED,
                ]:
                    self._pending_orders[submitted_order.id] = submitted_order
                else:
                    self._completed_orders.append(submitted_order)
                    self._update_execution_metrics(submitted_order)

                # Publish event
                self._publish_order_event(submitted_order)

                self.logger.info(
                    f"Order submitted: {trade.symbol} {trade.side.value} "
                    f"qty={trade.suggested_size:.2f} status={submitted_order.status.value}"
                )

            except Exception as e:
                self.logger.error(f"Error executing trade {trade.symbol}: {e}")

        return orders

    def _create_order(
        self, trade: CandidateTrade, mso: MarketStateObject
    ) -> Order:
        """Create an order from a candidate trade."""
        # Determine order type
        order_type = self._determine_order_type(trade, mso)

        # Calculate limit price if needed
        limit_price = None
        if order_type == OrderType.LIMIT:
            limit_price = self._calculate_limit_price(trade)

        order = Order(
            candidate_trade_id=trade.id,
            symbol=trade.symbol,
            side=trade.side,
            quantity=trade.suggested_size,
            order_type=order_type,
            limit_price=limit_price,
            strategy_name=trade.strategy_name,
            tags=[trade.timeframe.value, trade.setup_type],
        )

        return order

    def _determine_order_type(
        self, trade: CandidateTrade, mso: MarketStateObject
    ) -> OrderType:
        """Determine appropriate order type based on conditions."""
        # Use market orders outside regular hours for fills
        if mso.session != Session.REGULAR_HOURS:
            return OrderType.MARKET

        # Use market orders in high volatility for urgency
        if self.config.use_market_during_volatility:
            if mso.volatility.value == "high":
                return OrderType.MARKET

        return self.config.default_order_type

    def _calculate_limit_price(self, trade: CandidateTrade) -> float:
        """Calculate limit price with offset."""
        if trade.entry_price is None:
            return 0.0

        offset = trade.entry_price * (self.config.limit_offset_percent / 100)

        if trade.side == Side.BUY:
            # Buy slightly above to increase fill probability
            return trade.entry_price + offset
        else:
            # Sell slightly below
            return trade.entry_price - offset

    def _get_broker_for_trade(
        self, trade: CandidateTrade
    ) -> Optional[BrokerAdapter]:
        """Get appropriate broker for a trade."""
        asset_class = AssetClass(trade.asset_class)

        # Find broker that handles this asset class
        for name, broker in self._brokers.items():
            if asset_class in broker.config.asset_classes:
                return broker

        # Fall back to first available broker
        if self._brokers:
            return list(self._brokers.values())[0]

        return None

    def _get_broker_for_order(self, order: Order) -> Optional[BrokerAdapter]:
        """Get broker that submitted an order."""
        # In production, would track which broker submitted each order
        if self._brokers:
            return list(self._brokers.values())[0]
        return None

    def _create_broker_adapter(
        self, config: BrokerConfig
    ) -> Optional[BrokerAdapter]:
        """Create broker adapter based on type."""
        if config.broker_type == "simulated":
            return SimulatedBroker(config)

        # In production, would create adapters for real brokers:
        # elif config.broker_type == "alpaca":
        #     return AlpacaBroker(config)
        # elif config.broker_type == "ib":
        #     return IBBroker(config)
        # elif config.broker_type == "ccxt":
        #     return CCXTBroker(config)

        self.logger.warning(f"Unknown broker type: {config.broker_type}")
        return None

    def _update_execution_metrics(self, order: Order) -> None:
        """Update execution quality metrics."""
        self._order_count += 1

        if order.slippage is not None:
            self._total_slippage += order.slippage

        if order.status == OrderStatus.FILLED:
            filled = sum(
                1 for o in self._completed_orders if o.status == OrderStatus.FILLED
            )
            self._fill_rate = filled / max(len(self._completed_orders), 1)

    def _publish_order_event(self, order: Order) -> None:
        """Publish order event."""
        event_type = {
            OrderStatus.SUBMITTED: EventType.ORDER_SUBMITTED,
            OrderStatus.FILLED: EventType.ORDER_FILLED,
            OrderStatus.CANCELLED: EventType.ORDER_CANCELLED,
            OrderStatus.REJECTED: EventType.ORDER_REJECTED,
        }.get(order.status, EventType.ORDER_SUBMITTED)

        event = OrderEvent(
            event_type=event_type,
            order_id=order.id,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=order.limit_price,
            filled_price=order.average_fill_price,
            filled_quantity=order.filled_quantity,
            slippage=order.slippage,
        )
        self.publish_event(event)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if order_id not in self._pending_orders:
            return False

        order = self._pending_orders[order_id]
        broker = self._get_broker_for_order(order)

        if broker:
            success = await broker.cancel_order(order_id)
            if success:
                del self._pending_orders[order_id]
                order.status = OrderStatus.CANCELLED
                order.cancelled_at = datetime.utcnow()
                self._completed_orders.append(order)
                return True

        return False

    async def cancel_all_orders(self) -> int:
        """Cancel all pending orders."""
        cancelled = 0
        for order_id in list(self._pending_orders.keys()):
            if await self.cancel_order(order_id):
                cancelled += 1
        return cancelled

    def get_status(self) -> dict[str, Any]:
        """Get execution agent status."""
        return {
            "agent": self.name,
            "state": self.state.value,
            "brokers": list(self._brokers.keys()),
            "pending_orders": len(self._pending_orders),
            "completed_orders": len(self._completed_orders),
            "execution_metrics": {
                "order_count": self._order_count,
                "total_slippage": self._total_slippage,
                "fill_rate": self._fill_rate,
                "avg_slippage": (
                    self._total_slippage / self._order_count
                    if self._order_count > 0
                    else 0
                ),
            },
            "metrics": self.metrics.model_dump(),
        }
