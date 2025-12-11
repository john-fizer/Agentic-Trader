"""
Base ML Model class for D.A.T.A.

Provides interface and common functionality for ML models used in trading.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field
from loguru import logger


class ModelConfig(BaseModel):
    """Configuration for ML models."""

    name: str
    version: str = "1.0.0"
    model_type: str  # classifier, regressor, regime

    # Training parameters
    feature_names: list[str] = Field(default_factory=list)
    target_name: str = "target"
    lookback_periods: int = 20

    # Model file paths
    model_path: Optional[str] = None
    scaler_path: Optional[str] = None

    # Performance tracking
    train_date: Optional[datetime] = None
    train_samples: int = 0
    validation_score: float = 0.0


class ModelMetrics(BaseModel):
    """Performance metrics for a model."""

    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None

    mse: Optional[float] = None
    mae: Optional[float] = None
    r2: Optional[float] = None

    predictions_made: int = 0
    correct_predictions: int = 0
    last_prediction_time: Optional[datetime] = None


class BaseMLModel(ABC):
    """
    Abstract base class for all ML models in D.A.T.A.

    Models are used for:
    - Direction prediction (up/down/flat)
    - Volatility forecasting
    - Regime classification
    - Return prediction
    """

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self.metrics = ModelMetrics()
        self.logger = logger.bind(model=config.name)

        self._model: Any = None
        self._scaler: Any = None
        self._is_trained: bool = False

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @abstractmethod
    async def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        validation_split: float = 0.2,
    ) -> dict[str, float]:
        """
        Train the model.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target vector (n_samples,)
            validation_split: Fraction of data for validation

        Returns:
            Dictionary of training metrics
        """
        pass

    @abstractmethod
    async def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make predictions.

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Predictions array
        """
        pass

    @abstractmethod
    async def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Get prediction probabilities (for classifiers).

        Args:
            X: Feature matrix

        Returns:
            Probability matrix (n_samples, n_classes)
        """
        pass

    async def save(self, path: Optional[str] = None) -> str:
        """Save model to disk."""
        import joblib

        save_path = path or self.config.model_path
        if not save_path:
            save_path = f"data/models/{self.name}_{self.config.version}.joblib"

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "model": self._model,
            "scaler": self._scaler,
            "config": self.config.model_dump(),
            "metrics": self.metrics.model_dump(),
        }

        joblib.dump(model_data, save_path)
        self.config.model_path = save_path
        self.logger.info(f"Model saved to {save_path}")

        return save_path

    async def load(self, path: Optional[str] = None) -> bool:
        """Load model from disk."""
        import joblib

        load_path = path or self.config.model_path
        if not load_path or not Path(load_path).exists():
            self.logger.warning(f"Model file not found: {load_path}")
            return False

        model_data = joblib.load(load_path)

        self._model = model_data["model"]
        self._scaler = model_data.get("scaler")
        self._is_trained = True

        self.logger.info(f"Model loaded from {load_path}")
        return True

    def preprocess(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        """Preprocess features (scaling, normalization)."""
        from sklearn.preprocessing import StandardScaler

        if fit or self._scaler is None:
            self._scaler = StandardScaler()
            return self._scaler.fit_transform(X)

        return self._scaler.transform(X)

    def update_metrics(
        self, y_true: np.ndarray, y_pred: np.ndarray
    ) -> None:
        """Update model metrics based on predictions."""
        self.metrics.predictions_made += len(y_pred)

        if self.config.model_type == "classifier":
            correct = np.sum(y_true == y_pred)
            self.metrics.correct_predictions += correct
            self.metrics.accuracy = (
                self.metrics.correct_predictions / self.metrics.predictions_made
            )
        else:
            self.metrics.mse = float(np.mean((y_true - y_pred) ** 2))
            self.metrics.mae = float(np.mean(np.abs(y_true - y_pred)))

        self.metrics.last_prediction_time = datetime.utcnow()

    def get_status(self) -> dict[str, Any]:
        """Get model status."""
        return {
            "name": self.name,
            "version": self.config.version,
            "type": self.config.model_type,
            "is_trained": self._is_trained,
            "metrics": self.metrics.model_dump(),
            "config": self.config.model_dump(),
        }


class DirectionClassifier(BaseMLModel):
    """Classifier for predicting price direction (up/down/flat)."""

    def __init__(self, config: Optional[ModelConfig] = None) -> None:
        if config is None:
            config = ModelConfig(
                name="direction_classifier",
                model_type="classifier",
            )
        super().__init__(config)

    async def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        validation_split: float = 0.2,
    ) -> dict[str, float]:
        """Train the direction classifier."""
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, f1_score

        # Preprocess
        X_scaled = self.preprocess(X, fit=True)

        # Split
        X_train, X_val, y_train, y_val = train_test_split(
            X_scaled, y, test_size=validation_split, shuffle=False
        )

        # Train
        self._model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=20,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X_train, y_train)

        # Validate
        y_pred = self._model.predict(X_val)
        accuracy = accuracy_score(y_val, y_pred)
        f1 = f1_score(y_val, y_pred, average="weighted")

        self._is_trained = True
        self.config.train_date = datetime.utcnow()
        self.config.train_samples = len(X)
        self.config.validation_score = accuracy

        self.metrics.accuracy = accuracy
        self.metrics.f1_score = f1

        self.logger.info(f"Training complete: accuracy={accuracy:.3f}, f1={f1:.3f}")

        return {"accuracy": accuracy, "f1": f1}

    async def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict direction."""
        if not self._is_trained:
            raise ValueError("Model not trained")

        X_scaled = self.preprocess(X)
        return self._model.predict(X_scaled)

    async def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Get prediction probabilities."""
        if not self._is_trained:
            raise ValueError("Model not trained")

        X_scaled = self.preprocess(X)
        return self._model.predict_proba(X_scaled)


class VolatilityRegressor(BaseMLModel):
    """Regressor for predicting future volatility."""

    def __init__(self, config: Optional[ModelConfig] = None) -> None:
        if config is None:
            config = ModelConfig(
                name="volatility_regressor",
                model_type="regressor",
            )
        super().__init__(config)

    async def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        validation_split: float = 0.2,
    ) -> dict[str, float]:
        """Train the volatility regressor."""
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_squared_error, r2_score

        # Preprocess
        X_scaled = self.preprocess(X, fit=True)

        # Split
        X_train, X_val, y_train, y_val = train_test_split(
            X_scaled, y, test_size=validation_split, shuffle=False
        )

        # Train
        self._model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42,
        )
        self._model.fit(X_train, y_train)

        # Validate
        y_pred = self._model.predict(X_val)
        mse = mean_squared_error(y_val, y_pred)
        r2 = r2_score(y_val, y_pred)

        self._is_trained = True
        self.config.train_date = datetime.utcnow()
        self.config.train_samples = len(X)
        self.config.validation_score = r2

        self.metrics.mse = mse
        self.metrics.r2 = r2

        self.logger.info(f"Training complete: mse={mse:.6f}, r2={r2:.3f}")

        return {"mse": mse, "r2": r2}

    async def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict volatility."""
        if not self._is_trained:
            raise ValueError("Model not trained")

        X_scaled = self.preprocess(X)
        return self._model.predict(X_scaled)

    async def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Not applicable for regressor."""
        raise NotImplementedError("Regressor does not support predict_proba")
