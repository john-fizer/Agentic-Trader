"""
D.A.T.A. - Domain-Aware Trading Agent

Main entry point for the trading system.
"""

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger

from src.core.events import EventBus
from src.core.market_state import MarketStateObject

from src.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
from src.agents.initializer import InitializerAgent, InitializerConfig
from src.agents.strategy import StrategyManager, StrategyManagerConfig
from src.agents.strategy.strategies import TrendFollowingStrategy, MeanReversionStrategy
from src.agents.risk import RiskAgent, RiskAgentConfig
from src.agents.execution import ExecutionAgent, ExecutionAgentConfig
from src.agents.feedback import FeedbackAgent, FeedbackAgentConfig
from src.ml.features import FeatureEngine


class DATASystem:
    """
    Main D.A.T.A. trading system.

    Initializes and coordinates all agents to run the trading pipeline.
    """

    def __init__(self, config_path: str = "config") -> None:
        self.config_path = Path(config_path)
        self.event_bus = EventBus()
        self.orchestrator: Optional[Orchestrator] = None
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Configure logging
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure logging."""
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[agent]}</cyan> | "
            "<level>{message}</level>",
            level="INFO",
        )
        logger.add(
            "logs/data_{time:YYYY-MM-DD}.log",
            rotation="1 day",
            retention="30 days",
            level="DEBUG",
        )

    def _load_config(self, filename: str) -> dict:
        """Load YAML configuration file."""
        config_file = self.config_path / filename
        if config_file.exists():
            with open(config_file) as f:
                return yaml.safe_load(f)
        return {}

    async def initialize(self) -> None:
        """Initialize all system components."""
        logger.info("Initializing D.A.T.A. Trading System")

        # Load configurations
        strategies_config = self._load_config("strategies.yml")
        risk_config = self._load_config("risk.yml")
        data_config = self._load_config("data_sources.yml")

        # Create feature engine
        feature_engine = FeatureEngine()

        # Create orchestrator
        self.orchestrator = Orchestrator(
            config=OrchestratorConfig(),
            event_bus=self.event_bus,
        )

        # Create and register agents
        # 1. Initializer Agent
        initializer = InitializerAgent(
            config=InitializerConfig(),
            event_bus=self.event_bus,
        )
        self.orchestrator.register_agent(initializer)

        # 2. Strategy Manager
        strategy_manager = StrategyManager(
            config=StrategyManagerConfig(),
            event_bus=self.event_bus,
            feature_engine=feature_engine,
        )

        # Register built-in strategies
        strategy_manager.register_strategy(TrendFollowingStrategy())
        strategy_manager.register_strategy(MeanReversionStrategy())

        self.orchestrator.register_agent(strategy_manager)

        # 3. Risk Agent
        risk_agent = RiskAgent(
            config=RiskAgentConfig(),
            event_bus=self.event_bus,
        )
        self.orchestrator.register_agent(risk_agent)

        # 4. Execution Agent
        execution_agent = ExecutionAgent(
            config=ExecutionAgentConfig(),
            event_bus=self.event_bus,
        )
        self.orchestrator.register_agent(execution_agent)

        # 5. Feedback Agent
        feedback_agent = FeedbackAgent(
            config=FeedbackAgentConfig(),
            event_bus=self.event_bus,
        )
        self.orchestrator.register_agent(feedback_agent)

        # Start all agents
        await self.orchestrator.start()
        await self.orchestrator.start_all_agents()

        logger.info("D.A.T.A. System initialized successfully")

    async def run(self) -> None:
        """Run the main trading loop."""
        self._running = True
        logger.info("Starting main trading loop")

        try:
            while self._running:
                # Create fresh MSO for each cycle
                mso = MarketStateObject()

                # Run the processing pipeline
                results = await self.orchestrator.safe_process(mso)

                if results and not results.get("skipped"):
                    logger.info(
                        f"Cycle complete: "
                        f"candidates={len(results.get('candidate_trades', []))}, "
                        f"approved={len(results.get('approved_trades', []))}, "
                        f"orders={len(results.get('orders', []))}"
                    )

                # Wait for next cycle (or shutdown)
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=60.0,  # Process every minute
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Continue to next cycle

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            raise
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown the system gracefully."""
        logger.info("Shutting down D.A.T.A. System")
        self._running = False

        if self.orchestrator:
            await self.orchestrator.stop()

        logger.info("D.A.T.A. System shutdown complete")

    def request_shutdown(self) -> None:
        """Request system shutdown."""
        self._shutdown_event.set()


def main() -> None:
    """Main entry point."""
    # Create logs directory
    Path("logs").mkdir(exist_ok=True)

    # Create system
    system = DATASystem()

    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        system.request_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    try:
        asyncio.run(run_system(system))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


async def run_system(system: DATASystem) -> None:
    """Run the system."""
    await system.initialize()
    await system.run()


if __name__ == "__main__":
    main()
