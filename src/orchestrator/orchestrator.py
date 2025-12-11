"""
Orchestrator Agent - The "brainstem" of the D.A.T.A. system.

The Orchestrator is responsible for:
- Listening for events (new bars, macro events, risk triggers)
- Triggering agents in the correct sequence
- Enforcing global constraints (max daily loss, max leverage, kill switch)
- Managing the overall system lifecycle
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

from pydantic import BaseModel, Field
from loguru import logger

from src.agents.base import AgentConfig, AgentState, BaseAgent
from src.core.events import Event, EventBus, EventType
from src.core.market_state import MarketStateObject, Regime
from src.core.trade import CandidateTrade, Order, PortfolioSnapshot


class GlobalConstraints(BaseModel):
    """Global constraints enforced by the orchestrator."""

    # Daily limits
    max_daily_loss_percent: float = 2.0  # Max daily loss as % of equity
    max_daily_loss_amount: Optional[float] = None  # Absolute max daily loss

    # Leverage and exposure
    max_leverage: float = 2.0
    max_gross_exposure_percent: float = 200.0
    max_net_exposure_percent: float = 100.0

    # Position limits
    max_positions: int = 20
    max_position_size_percent: float = 10.0  # Max single position as % of equity
    max_sector_concentration_percent: float = 30.0

    # Operational limits
    max_orders_per_minute: int = 60
    max_daily_trades: int = 100

    # Kill switch thresholds
    kill_switch_drawdown_percent: float = 5.0  # Auto-stop if daily DD exceeds this
    kill_switch_loss_streak: int = 10  # Auto-stop after N consecutive losses


class OrchestratorConfig(AgentConfig):
    """Configuration for the Orchestrator."""

    name: str = "orchestrator"
    constraints: GlobalConstraints = Field(default_factory=GlobalConstraints)

    # Processing settings
    process_on_new_bar: bool = True
    process_interval_seconds: int = 60  # Fallback processing interval

    # Agent sequence
    agent_sequence: list[str] = Field(
        default_factory=lambda: [
            "initializer",
            "strategy",
            "risk",
            "execution",
            "feedback",
        ]
    )


class OrchestratorState(BaseModel):
    """Current state of the orchestrator."""

    is_trading_enabled: bool = True
    kill_switch_active: bool = False
    kill_switch_reason: Optional[str] = None

    # Daily tracking
    daily_realized_pnl: float = 0.0
    daily_trades: int = 0
    consecutive_losses: int = 0

    # Timestamps
    last_process_time: Optional[datetime] = None
    trading_start_time: Optional[datetime] = None
    kill_switch_triggered_at: Optional[datetime] = None


class Orchestrator(BaseAgent):
    """
    The Orchestrator is the central coordinator for the D.A.T.A. system.

    It manages the flow of information between agents and enforces
    global constraints to protect the portfolio.
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        event_bus: EventBus,
    ) -> None:
        super().__init__(config, event_bus)
        self.config: OrchestratorConfig = config
        self.orchestrator_state = OrchestratorState()

        # Agent registry
        self._agents: dict[str, BaseAgent] = {}

        # Current market state
        self._current_mso: Optional[MarketStateObject] = None

        # Processing lock to prevent concurrent runs
        self._processing_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the orchestrator."""
        self.logger.info("Initializing Orchestrator")

        # Subscribe to relevant events
        self.subscribe(EventType.NEW_BAR, self._on_new_bar)
        self.subscribe(EventType.RISK_LIMIT_BREACH, self._on_risk_breach)
        self.subscribe(EventType.MACRO_EVENT, self._on_macro_event)
        self.subscribe(EventType.KILL_SWITCH, self._on_kill_switch)

        self.orchestrator_state.trading_start_time = datetime.utcnow()
        self.logger.info("Orchestrator initialized")

    async def shutdown(self) -> None:
        """Shutdown the orchestrator and all agents."""
        self.logger.info("Shutting down Orchestrator")

        # Stop all agents in reverse order
        for agent_name in reversed(self.config.agent_sequence):
            if agent_name in self._agents:
                try:
                    await self._agents[agent_name].stop()
                except Exception as e:
                    self.logger.error(f"Error stopping agent {agent_name}: {e}")

        self.logger.info("Orchestrator shutdown complete")

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the orchestrator."""
        self._agents[agent.name] = agent
        self.logger.info(f"Registered agent: {agent.name}")

    async def start_all_agents(self) -> None:
        """Start all registered agents in sequence."""
        for agent_name in self.config.agent_sequence:
            if agent_name in self._agents:
                await self._agents[agent_name].start()

    async def process(self, mso: MarketStateObject, **kwargs: Any) -> dict[str, Any]:
        """
        Run the full agent processing pipeline.

        This is the main processing loop that coordinates all agents.
        """
        async with self._processing_lock:
            return await self._run_pipeline(mso)

    async def _run_pipeline(self, mso: MarketStateObject) -> dict[str, Any]:
        """Run the agent pipeline."""
        results: dict[str, Any] = {
            "timestamp": datetime.utcnow(),
            "mso": None,
            "candidate_trades": [],
            "approved_trades": [],
            "orders": [],
            "skipped": False,
        }

        # Check if trading is enabled
        if not self.orchestrator_state.is_trading_enabled:
            results["skipped"] = True
            results["skip_reason"] = "Trading disabled"
            return results

        if self.orchestrator_state.kill_switch_active:
            results["skipped"] = True
            results["skip_reason"] = f"Kill switch active: {self.orchestrator_state.kill_switch_reason}"
            return results

        # Check global constraints
        constraint_check = self._check_global_constraints()
        if not constraint_check["passed"]:
            results["skipped"] = True
            results["skip_reason"] = constraint_check["reason"]
            return results

        try:
            # Step 1: Initializer - Build/Update MSO
            if "initializer" in self._agents:
                mso = await self._agents["initializer"].safe_process(mso) or mso
            results["mso"] = mso
            self._current_mso = mso

            # Publish MSO update event
            self.publish_event(Event(event_type=EventType.MSO_UPDATED, data={"mso_summary": mso.summary}))

            # Step 2: Strategy - Generate candidate trades
            candidate_trades: list[CandidateTrade] = []
            if "strategy" in self._agents:
                trades = await self._agents["strategy"].safe_process(mso)
                if trades:
                    candidate_trades = trades
            results["candidate_trades"] = candidate_trades

            # Step 3: Risk - Filter and size trades
            approved_trades: list[CandidateTrade] = []
            if "risk" in self._agents and candidate_trades:
                approved = await self._agents["risk"].safe_process(
                    mso, candidate_trades=candidate_trades
                )
                if approved:
                    approved_trades = approved
            results["approved_trades"] = approved_trades

            # Step 4: Execution - Submit orders
            orders: list[Order] = []
            if "execution" in self._agents and approved_trades:
                submitted = await self._agents["execution"].safe_process(
                    mso, trades=approved_trades
                )
                if submitted:
                    orders = submitted
            results["orders"] = orders

            # Step 5: Feedback - Log and learn
            if "feedback" in self._agents:
                await self._agents["feedback"].safe_process(
                    mso,
                    candidate_trades=candidate_trades,
                    approved_trades=approved_trades,
                    orders=orders,
                )

            self.orchestrator_state.last_process_time = datetime.utcnow()

        except Exception as e:
            self.logger.error(f"Pipeline error: {e}")
            results["error"] = str(e)

        return results

    def _check_global_constraints(self) -> dict[str, Any]:
        """Check if global constraints allow trading."""
        constraints = self.config.constraints
        state = self.orchestrator_state

        # Check daily loss limit
        if constraints.max_daily_loss_amount:
            if abs(state.daily_realized_pnl) >= constraints.max_daily_loss_amount:
                return {
                    "passed": False,
                    "reason": f"Daily loss limit reached: ${state.daily_realized_pnl:.2f}",
                }

        # Check consecutive losses
        if state.consecutive_losses >= constraints.kill_switch_loss_streak:
            self._trigger_kill_switch(
                f"Consecutive losses: {state.consecutive_losses}"
            )
            return {"passed": False, "reason": "Consecutive loss limit reached"}

        # Check daily trade limit
        if state.daily_trades >= constraints.max_daily_trades:
            return {
                "passed": False,
                "reason": f"Daily trade limit reached: {state.daily_trades}",
            }

        return {"passed": True, "reason": None}

    def _trigger_kill_switch(self, reason: str) -> None:
        """Activate the kill switch."""
        self.orchestrator_state.kill_switch_active = True
        self.orchestrator_state.kill_switch_reason = reason
        self.orchestrator_state.kill_switch_triggered_at = datetime.utcnow()

        self.logger.critical(f"KILL SWITCH ACTIVATED: {reason}")

        self.publish_event(
            Event(
                event_type=EventType.KILL_SWITCH,
                data={"reason": reason, "triggered_at": datetime.utcnow().isoformat()},
            )
        )

    def reset_kill_switch(self) -> None:
        """Manually reset the kill switch."""
        self.orchestrator_state.kill_switch_active = False
        self.orchestrator_state.kill_switch_reason = None
        self.orchestrator_state.kill_switch_triggered_at = None
        self.logger.warning("Kill switch manually reset")

    def reset_daily_counters(self) -> None:
        """Reset daily counters (call at start of each trading day)."""
        self.orchestrator_state.daily_realized_pnl = 0.0
        self.orchestrator_state.daily_trades = 0
        self.orchestrator_state.consecutive_losses = 0
        self.logger.info("Daily counters reset")

    def enable_trading(self) -> None:
        """Enable trading."""
        self.orchestrator_state.is_trading_enabled = True
        self.logger.info("Trading enabled")

    def disable_trading(self) -> None:
        """Disable trading."""
        self.orchestrator_state.is_trading_enabled = False
        self.logger.warning("Trading disabled")

    # Event handlers
    def _on_new_bar(self, event: Event) -> None:
        """Handle new bar event."""
        self.logger.debug(f"New bar event: {event.data}")
        # Processing will be triggered by the main loop

    def _on_risk_breach(self, event: Event) -> None:
        """Handle risk breach event."""
        self.logger.warning(f"Risk breach: {event.data}")

        severity = event.data.get("severity", "warning")
        if severity == "critical":
            self._trigger_kill_switch(f"Critical risk breach: {event.data.get('message', 'Unknown')}")

    def _on_macro_event(self, event: Event) -> None:
        """Handle macro event."""
        self.logger.info(f"Macro event: {event.data}")

    def _on_kill_switch(self, event: Event) -> None:
        """Handle kill switch event from other sources."""
        if not self.orchestrator_state.kill_switch_active:
            reason = event.data.get("reason", "External trigger")
            self._trigger_kill_switch(reason)

    def get_status(self) -> dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "state": self.state.value,
            "orchestrator_state": self.orchestrator_state.model_dump(),
            "constraints": self.config.constraints.model_dump(),
            "agents": {
                name: agent.get_metrics() for name, agent in self._agents.items()
            },
            "current_mso_summary": self._current_mso.summary if self._current_mso else None,
        }
