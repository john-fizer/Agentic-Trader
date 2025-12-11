"""
D.A.T.A. Agent Framework

This module contains all specialized agents that make up the trading system:
- Orchestrator: Supervises all agents and enforces global rules
- Initializer: Builds the Market State Object (MSO)
- Strategy: Generates trade ideas per asset class/timeframe
- Risk: Evaluates trades and enforces risk limits
- Execution: Routes and manages orders
- Feedback: Learns from outcomes and updates models
"""

from src.agents.base import BaseAgent, AgentState, AgentConfig

__all__ = [
    "BaseAgent",
    "AgentState",
    "AgentConfig",
]
