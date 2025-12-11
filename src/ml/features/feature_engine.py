"""
Feature Engineering Engine for D.A.T.A.

Computes features for machine learning models and strategies:
- Price-based features (returns, volatility, trends)
- Structure-based features (support/resistance, volume profile)
- Microstructure features (spread, order book)
- Options-specific features (Greeks, IV)
- Regime features (market internals, breadth)
"""

from datetime import datetime
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, Field
from loguru import logger


class FeatureConfig(BaseModel):
    """Configuration for feature computation."""

    # Lookback periods
    return_periods: list[int] = Field(default_factory=lambda: [1, 5, 10, 20, 60])
    volatility_periods: list[int] = Field(default_factory=lambda: [10, 20, 60])
    ma_periods: list[int] = Field(default_factory=lambda: [10, 20, 50, 200])

    # Feature toggles
    compute_momentum: bool = True
    compute_volatility: bool = True
    compute_trend: bool = True
    compute_volume: bool = True
    compute_microstructure: bool = False


class FeatureEngine:
    """
    Computes features from market data for ML models and strategies.

    Features are computed lazily and cached for efficiency.
    """

    def __init__(self, config: Optional[FeatureConfig] = None) -> None:
        self.config = config or FeatureConfig()
        self.logger = logger.bind(component="feature_engine")

        # Feature cache
        self._cache: dict[str, dict[str, float]] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds: int = 60

    async def compute_features(
        self,
        symbols: list[str],
        price_data: dict[str, dict],
    ) -> dict[str, dict[str, float]]:
        """
        Compute features for multiple symbols.

        Args:
            symbols: List of symbols to compute features for
            price_data: Price data per symbol (must include OHLCV)

        Returns:
            Dictionary mapping symbol to feature dictionary
        """
        features = {}

        for symbol in symbols:
            if symbol not in price_data:
                features[symbol] = {}
                continue

            data = price_data[symbol]
            features[symbol] = self._compute_symbol_features(data)

        return features

    def _compute_symbol_features(self, data: dict) -> dict[str, float]:
        """Compute all features for a single symbol."""
        features = {}

        # Extract arrays
        close = np.array(data.get("close", []))
        high = np.array(data.get("high", close))
        low = np.array(data.get("low", close))
        volume = np.array(data.get("volume", []))

        if len(close) < 20:
            return features

        # Price-based features
        if self.config.compute_momentum:
            features.update(self._compute_momentum_features(close))

        if self.config.compute_volatility:
            features.update(self._compute_volatility_features(close, high, low))

        if self.config.compute_trend:
            features.update(self._compute_trend_features(close))

        if self.config.compute_volume and len(volume) > 0:
            features.update(self._compute_volume_features(close, volume))

        return features

    def _compute_momentum_features(self, close: np.ndarray) -> dict[str, float]:
        """Compute momentum/return features."""
        features = {}

        # Returns
        for period in self.config.return_periods:
            if len(close) > period:
                ret = (close[-1] - close[-period - 1]) / close[-period - 1]
                features[f"return_{period}d"] = float(ret)

        # RSI
        if len(close) >= 14:
            features["rsi_14"] = self._compute_rsi(close, 14)

        # MACD
        if len(close) >= 26:
            macd, signal, hist = self._compute_macd(close)
            features["macd"] = float(macd)
            features["macd_signal"] = float(signal)
            features["macd_hist"] = float(hist)

        # Rate of Change
        if len(close) > 10:
            features["roc_10"] = float((close[-1] - close[-11]) / close[-11] * 100)

        return features

    def _compute_volatility_features(
        self, close: np.ndarray, high: np.ndarray, low: np.ndarray
    ) -> dict[str, float]:
        """Compute volatility features."""
        features = {}

        returns = np.diff(close) / close[:-1]

        # Rolling volatility
        for period in self.config.volatility_periods:
            if len(returns) >= period:
                vol = np.std(returns[-period:]) * np.sqrt(252)
                features[f"volatility_{period}d"] = float(vol)

        # ATR
        if len(close) >= 14:
            atr = self._compute_atr(high, low, close, 14)
            features["atr_14"] = float(atr)
            features["atr_percent"] = float(atr / close[-1] * 100)

        # Bollinger Band position
        if len(close) >= 20:
            sma = np.mean(close[-20:])
            std = np.std(close[-20:])
            upper = sma + 2 * std
            lower = sma - 2 * std
            bb_pos = (close[-1] - lower) / (upper - lower) if upper != lower else 0.5
            features["bb_position"] = float(bb_pos)
            features["bb_width"] = float((upper - lower) / sma * 100)

        return features

    def _compute_trend_features(self, close: np.ndarray) -> dict[str, float]:
        """Compute trend features."""
        features = {}

        # Moving averages
        for period in self.config.ma_periods:
            if len(close) >= period:
                ma = np.mean(close[-period:])
                features[f"sma_{period}"] = float(ma)
                features[f"price_vs_sma_{period}"] = float((close[-1] - ma) / ma)

        # MA crossovers
        if len(close) >= 50:
            sma_10 = np.mean(close[-10:])
            sma_50 = np.mean(close[-50:])
            features["ma_cross_10_50"] = float(sma_10 - sma_50)

        # Trend strength (using linear regression slope)
        if len(close) >= 20:
            x = np.arange(20)
            slope, _ = np.polyfit(x, close[-20:], 1)
            features["trend_slope_20"] = float(slope / close[-20])

        # ADX approximation
        if len(close) >= 14:
            features["adx_14"] = self._compute_adx_approx(close)

        return features

    def _compute_volume_features(
        self, close: np.ndarray, volume: np.ndarray
    ) -> dict[str, float]:
        """Compute volume features."""
        features = {}

        if len(volume) < 20:
            return features

        # Volume ratio
        avg_vol = np.mean(volume[-20:])
        features["volume_ratio"] = float(volume[-1] / avg_vol) if avg_vol > 0 else 1.0

        # Volume trend
        vol_5 = np.mean(volume[-5:])
        vol_20 = np.mean(volume[-20:])
        features["volume_trend"] = float(vol_5 / vol_20) if vol_20 > 0 else 1.0

        # On-Balance Volume
        if len(close) == len(volume):
            obv = self._compute_obv(close, volume)
            features["obv_norm"] = float(obv / avg_vol) if avg_vol > 0 else 0

        # Volume-weighted momentum
        if len(close) >= 10:
            price_change = close[-10:] - close[-11:-1]
            vol_weighted = np.sum(price_change * volume[-10:]) / np.sum(volume[-10:])
            features["vwap_momentum"] = float(vol_weighted)

        return features

    def _compute_rsi(self, close: np.ndarray, period: int = 14) -> float:
        """Compute RSI."""
        deltas = np.diff(close[-period - 1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _compute_macd(
        self, close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[float, float, float]:
        """Compute MACD."""
        ema_fast = self._compute_ema(close, fast)
        ema_slow = self._compute_ema(close, slow)
        macd_line = ema_fast - ema_slow

        # Signal line (simplified as SMA of recent MACD values)
        if len(close) >= slow + signal:
            signal_line = np.mean([
                self._compute_ema(close[:-i], fast) - self._compute_ema(close[:-i], slow)
                for i in range(signal)
            ])
        else:
            signal_line = macd_line

        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def _compute_ema(self, data: np.ndarray, period: int) -> float:
        """Compute Exponential Moving Average."""
        if len(data) < period:
            return float(np.mean(data))

        multiplier = 2 / (period + 1)
        ema = np.mean(data[:period])

        for price in data[period:]:
            ema = (price - ema) * multiplier + ema

        return float(ema)

    def _compute_atr(
        self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
    ) -> float:
        """Compute Average True Range."""
        true_ranges = []
        for i in range(1, min(len(high), period + 1)):
            tr = max(
                high[-i] - low[-i],
                abs(high[-i] - close[-i - 1]) if i < len(close) else high[-i] - low[-i],
                abs(low[-i] - close[-i - 1]) if i < len(close) else high[-i] - low[-i],
            )
            true_ranges.append(tr)

        return float(np.mean(true_ranges)) if true_ranges else 0.0

    def _compute_adx_approx(self, close: np.ndarray, period: int = 14) -> float:
        """Approximate ADX using price efficiency."""
        if len(close) < period:
            return 50.0

        # Use directional efficiency as ADX proxy
        total_move = abs(close[-1] - close[-period])
        sum_moves = sum(abs(close[-i] - close[-i - 1]) for i in range(1, period))

        efficiency = (total_move / sum_moves * 100) if sum_moves > 0 else 50

        return float(min(100, efficiency))

    def _compute_obv(self, close: np.ndarray, volume: np.ndarray) -> float:
        """Compute On-Balance Volume (normalized)."""
        obv = 0.0
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv += volume[i]
            elif close[i] < close[i - 1]:
                obv -= volume[i]

        return obv

    def get_feature_names(self) -> list[str]:
        """Get list of all feature names."""
        names = []

        # Momentum
        if self.config.compute_momentum:
            for p in self.config.return_periods:
                names.append(f"return_{p}d")
            names.extend(["rsi_14", "macd", "macd_signal", "macd_hist", "roc_10"])

        # Volatility
        if self.config.compute_volatility:
            for p in self.config.volatility_periods:
                names.append(f"volatility_{p}d")
            names.extend(["atr_14", "atr_percent", "bb_position", "bb_width"])

        # Trend
        if self.config.compute_trend:
            for p in self.config.ma_periods:
                names.extend([f"sma_{p}", f"price_vs_sma_{p}"])
            names.extend(["ma_cross_10_50", "trend_slope_20", "adx_14"])

        # Volume
        if self.config.compute_volume:
            names.extend(["volume_ratio", "volume_trend", "obv_norm", "vwap_momentum"])

        return names
