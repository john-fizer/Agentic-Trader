"""Built-in trading strategies."""

from src.agents.strategy.strategies.trend_following import TrendFollowingStrategy
from src.agents.strategy.strategies.mean_reversion import MeanReversionStrategy

__all__ = ["TrendFollowingStrategy", "MeanReversionStrategy"]
