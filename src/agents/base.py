"""
Base Agent class for all D.A.T.A. agents.

Provides common functionality and interfaces that all agents must implement.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from loguru import logger

from src.core.events import Event, EventBus, EventType
from src.core.market_state import MarketStateObject


class AgentState(str, Enum):
    """Agent operational state."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class AgentConfig(BaseModel):
    """Base configuration for all agents."""

    name: str
    enabled: bool = True
    log_level: str = "INFO"
    heartbeat_interval_seconds: int = 60


class AgentMetrics(BaseModel):
    """Metrics tracked by each agent."""

    invocations: int = 0
    successful_invocations: int = 0
    failed_invocations: int = 0
    total_execution_time_ms: float = 0.0
    last_invocation: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None


class BaseAgent(ABC):
    """
    Abstract base class for all D.A.T.A. agents.

    Each agent must implement:
    - initialize(): Setup routine
    - process(): Main processing logic
    - shutdown(): Cleanup routine

    Agents communicate through:
    - EventBus: For async pub/sub messaging
    - MarketStateObject: Shared context passed to all agents
    """

    def __init__(
        self,
        config: AgentConfig,
        event_bus: EventBus,
    ) -> None:
        self.config = config
        self.event_bus = event_bus
        self.state = AgentState.INITIALIZING
        self.metrics = AgentMetrics()

        # Set up logger for this agent
        self.logger = logger.bind(agent=config.name)

    @property
    def name(self) -> str:
        """Agent name."""
        return self.config.name

    @property
    def is_running(self) -> bool:
        """Check if agent is in running state."""
        return self.state == AgentState.RUNNING

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the agent.

        Called once when the system starts. Use for:
        - Loading models
        - Connecting to databases
        - Subscribing to events
        - Validating configuration
        """
        pass

    @abstractmethod
    async def process(self, mso: MarketStateObject, **kwargs: Any) -> Any:
        """
        Main processing logic for the agent.

        Args:
            mso: The current Market State Object
            **kwargs: Additional arguments specific to each agent

        Returns:
            Agent-specific output (e.g., candidate trades, approved trades, orders)
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shutdown the agent gracefully.

        Called when the system is stopping. Use for:
        - Closing connections
        - Saving state
        - Cleanup
        """
        pass

    async def start(self) -> None:
        """Start the agent."""
        try:
            await self.initialize()
            self.state = AgentState.RUNNING
            self.logger.info(f"Agent {self.name} started successfully")
        except Exception as e:
            self.state = AgentState.ERROR
            self.metrics.last_error = str(e)
            self.metrics.last_error_time = datetime.utcnow()
            self.logger.error(f"Agent {self.name} failed to start: {e}")
            raise

    async def stop(self) -> None:
        """Stop the agent."""
        try:
            await self.shutdown()
            self.state = AgentState.STOPPED
            self.logger.info(f"Agent {self.name} stopped")
        except Exception as e:
            self.logger.error(f"Error stopping agent {self.name}: {e}")
            raise

    def pause(self) -> None:
        """Pause the agent."""
        self.state = AgentState.PAUSED
        self.logger.info(f"Agent {self.name} paused")

    def resume(self) -> None:
        """Resume the agent."""
        self.state = AgentState.RUNNING
        self.logger.info(f"Agent {self.name} resumed")

    async def safe_process(self, mso: MarketStateObject, **kwargs: Any) -> Optional[Any]:
        """
        Wrapper around process() with error handling and metrics.

        Use this method instead of calling process() directly.
        """
        if not self.is_running:
            self.logger.warning(f"Agent {self.name} is not running, skipping process")
            return None

        start_time = datetime.utcnow()
        self.metrics.invocations += 1
        self.metrics.last_invocation = start_time

        try:
            result = await self.process(mso, **kwargs)
            self.metrics.successful_invocations += 1
            return result
        except Exception as e:
            self.metrics.failed_invocations += 1
            self.metrics.last_error = str(e)
            self.metrics.last_error_time = datetime.utcnow()
            self.logger.error(f"Agent {self.name} process error: {e}")
            raise
        finally:
            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics.total_execution_time_ms += elapsed

    def publish_event(self, event: Event) -> None:
        """Publish an event to the event bus."""
        event.source = self.name
        self.event_bus.publish(event)

    def subscribe(self, event_type: EventType, handler: Any) -> None:
        """Subscribe to events of a specific type."""
        self.event_bus.subscribe(event_type, handler)

    def get_metrics(self) -> dict[str, Any]:
        """Get agent metrics as dictionary."""
        return {
            "name": self.name,
            "state": self.state.value,
            "metrics": self.metrics.model_dump(),
        }
