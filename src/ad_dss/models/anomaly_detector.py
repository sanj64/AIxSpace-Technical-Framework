"""Anomaly detection with unified interface: LSTM AE, Isolation Forest, Z-score."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler

from ad_dss.common.logging_config import get_logger
from ad_dss.common.schemas import AnomalyResult
from ad_dss.data.preprocessing import clean, create_windows, normalize

logger = get_logger(__name__)

os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")


class AnomalyDetector:
    """Unified anomaly detector supporting LSTM AE, Isolation Forest, and Z-score.

    All three backends expose the same train/score/detect interface so that
    the rest of the pipeline is backend-agnostic.
    """

    def __init__(self, config: dict, method: str = "lstm") -> None:
        self.method = method
        self.cfg = config
        ad_cfg = config.get("anomaly_detector", config)
        self.window_size: int = ad_cfg.get("window_size", 30)
        self.latent_dim: int = ad_cfg.get("latent_dim", 32)
        self.model_path = Path(ad_cfg.get("model_path", "models/lstm_autoencoder.keras"))
        self.thresholds: dict[str, float] = ad_cfg.get("reconstruction_thresholds", {"default": 0.1})
        self.threshold_pct: float = float(ad_cfg.get("threshold_percentile", 95.0))
        train_cfg = config.get("training", {})
        self.epochs: int = int(train_cfg.get("epochs", 20))
        self.batch_size: int = int(train_cfg.get("batch_size", 32))
        self.val_split: float = float(train_cfg.get("validation_split", 0.1))
        self.early_stopping_patience: int = int(train_cfg.get("early_stopping_patience", 3))

        # Backend-specific state
        self._model: Any = None  # Keras Model | IsolationForest | None
        self._scaler: Any = None  # MinMaxScaler for LSTM
        self._threshold: float | None = None  # learned from training data
        self._zscore_cfg = ad_cfg.get("zscore", {})
        self._if_cfg = ad_cfg.get("isolation_forest", {})

    # ── Public API ──────────────────────────────────────────────────────────

    def train(self, df: pd.DataFrame) -> None:
        """Train the detector on clean numeric telemetry."""
        df_clean = clean(df)
        if self.method == "lstm":
            self._train_lstm(df_clean)
        elif self.method == "isolation_forest":
            self._train_if(df_clean)
        elif self.method == "zscore":
            logger.info("Z-score detector has no training step.")
        else:
            raise ValueError(f"Unknown method: {self.method}")

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """Return per-sample anomaly scores (higher = more anomalous)."""
        df_clean = clean(df)
        if self.method == "lstm":
            return self._score_lstm(df_clean)
        if self.method == "isolation_forest":
            return self._score_if(df_clean)
        if self.method == "zscore":
            return self._score_zscore(df_clean)
        raise ValueError(f"Unknown method: {self.method}")

    def detect(self, df: pd.DataFrame, subsystem: str = "default") -> list[AnomalyResult]:
        """Score + threshold → list of AnomalyResult (one per aligned sample)."""
        df_clean = clean(df)
        scores = self.score(df_clean)
        threshold = self._get_threshold(subsystem, scores)

        # Align scores back to DataFrame index
        if self.method == "lstm":
            idx = df_clean.index[self.window_size - 1 :]
        else:
            idx = df_clean.index[: len(scores)]

        max_s = scores.max() if scores.max() > 0 else 1.0
        results: list[AnomalyResult] = []
        for i, (ts, sc) in enumerate(zip(idx, scores)):
            results.append(
                AnomalyResult(
                    timestamp=ts,
                    subsystem=subsystem,
                    reconstruction_error=float(sc),
                    anomaly_flag=int(sc > threshold),
                    score=float(sc / max_s),
                )
            )
        n_anomalies = sum(r.anomaly_flag for r in results)
        logger.info(
            "detect(): method=%s subsystem=%s anomalies=%d/%d threshold=%.6f",
            self.method,
            subsystem,
            n_anomalies,
            len(results),
            threshold,
        )
        return results

    def save(self, path: Path | None = None) -> None:
        """Persist the trained model/state to disk."""
        path = Path(path) if path else self.model_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.method == "lstm" and self._model is not None:
            self._model.save(str(path))
            if self._scaler is not None:
                joblib.dump(self._scaler, path.with_suffix(".scaler.pkl"))
            logger.info("Saved LSTM model to %s", path)
        elif self.method == "isolation_forest" and self._model is not None:
            joblib.dump(self._model, path.with_suffix(".if.pkl"))
            logger.info("Saved IF model to %s", path)

    def load(self, path: Path | None = None) -> None:
        """Load a previously saved model from disk."""
        path = Path(path) if path else self.model_path
        if self.method == "lstm":
            from tensorflow.keras.models import load_model  # type: ignore[import]

            self._model = load_model(str(path))
            scaler_path = path.with_suffix(".scaler.pkl")
            if scaler_path.exists():
                self._scaler = joblib.load(scaler_path)
            logger.info("Loaded LSTM model from %s", path)
        elif self.method == "isolation_forest":
            self._model = joblib.load(path.with_suffix(".if.pkl"))
            logger.info("Loaded IF model from %s", path)

    # ── LSTM AE backend ─────────────────────────────────────────────────────

    def _train_lstm(self, df: pd.DataFrame) -> None:
        from tensorflow.keras.callbacks import EarlyStopping  # type: ignore[import]
        from tensorflow.keras.layers import LSTM, Dense, Input, RepeatVector, TimeDistributed  # type: ignore[import]
        from tensorflow.keras.models import Model  # type: ignore[import]

        normed, self._scaler = normalize(df, method="minmax")
        X = create_windows(normed.values, self.window_size)
        n_features = X.shape[2]

        inp = Input(shape=(self.window_size, n_features))
        enc = LSTM(self.latent_dim, activation="tanh")(inp)
        rep = RepeatVector(self.window_size)(enc)
        dec = LSTM(self.latent_dim, activation="tanh", return_sequences=True)(rep)
        out = TimeDistributed(Dense(n_features))(dec)
        model = Model(inp, out)
        model.compile(optimizer="adam", loss="mse")

        cb = EarlyStopping(monitor="loss", patience=self.early_stopping_patience, restore_best_weights=True)
        val_split = self.val_split if len(X) > 20 else 0.0
        model.fit(
            X, X,
            epochs=self.epochs,
            batch_size=self.batch_size,
            validation_split=val_split,
            callbacks=[cb],
            verbose=0,
        )
        self._model = model
        # Compute training-set threshold
        recon = model.predict(X, verbose=0)
        train_scores = np.mean((X - recon) ** 2, axis=(1, 2))
        self._threshold = float(np.percentile(train_scores, self.threshold_pct))
        logger.info("LSTM trained: threshold=%.6f (%.1f pct)", self._threshold, self.threshold_pct)

    def _score_lstm(self, df: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("LSTM model not trained or loaded.")
        if self._scaler is not None:
            normed, _ = normalize(df, scaler=self._scaler, fit=False)
        else:
            normed, _ = normalize(df, method="minmax")
        X = create_windows(normed.values, self.window_size)
        recon = self._model.predict(X, verbose=0)
        return np.mean((X - recon) ** 2, axis=(1, 2))

    # ── Isolation Forest backend ─────────────────────────────────────────────

    def _train_if(self, df: pd.DataFrame) -> None:
        contamination = self._if_cfg.get("contamination", 0.05)
        n_estimators = self._if_cfg.get("n_estimators", 100)
        rs = self._if_cfg.get("random_state", 42)
        self._model = IsolationForest(
            n_estimators=n_estimators, contamination=contamination, random_state=rs
        )
        self._model.fit(df.values)
        logger.info("IsolationForest trained on shape=%s", df.shape)

    def _score_if(self, df: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("IsolationForest not trained or loaded.")
        # decision_function: higher = more normal; negate so higher = more anomalous
        return -self._model.decision_function(df.values)

    # ── Z-score backend ──────────────────────────────────────────────────────

    def _score_zscore(self, df: pd.DataFrame) -> np.ndarray:
        win = int(self._zscore_cfg.get("window", 60))
        min_periods = int(self._zscore_cfg.get("min_periods", 10))

        mu = df.rolling(win, min_periods=min_periods).mean()
        sigma = df.rolling(win, min_periods=min_periods).std().replace(0, 1e-9)
        z = ((df - mu) / sigma).abs()
        # Max z-score across all channels per row
        return z.max(axis=1).fillna(0).values

    # ── Threshold helpers ────────────────────────────────────────────────────

    def _get_threshold(self, subsystem: str, scores: np.ndarray) -> float:
        # Priority: 1) config per-subsystem, 2) learned, 3) percentile of current scores
        cfg_thr = self.thresholds.get(subsystem) or self.thresholds.get("default")
        if self.method == "zscore":
            return float(self._zscore_cfg.get("z_threshold", 3.5))
        if self.method == "isolation_forest":
            return float(cfg_thr) if cfg_thr is not None else float(np.percentile(scores, self.threshold_pct))
        # LSTM: prefer learned threshold, fall back to config
        if self._threshold is not None:
            return self._threshold
        if cfg_thr is not None:
            return float(cfg_thr)
        return float(np.percentile(scores, self.threshold_pct))


def build_detector(config: dict, method: str = "lstm") -> AnomalyDetector:
    """Factory function for creating a configured AnomalyDetector."""
    return AnomalyDetector(config, method=method)
