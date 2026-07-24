"""Tests for models/anomaly_detector.py — all three backends."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from ad_dss.models.anomaly_detector import AnomalyDetector, build_detector

CONFIG_PATH = "config/settings.yaml"


@pytest.fixture()
def config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture()
def small_df() -> pd.DataFrame:
    """80-row synthetic time series with 3 numeric channels."""
    rng = np.random.default_rng(0)
    idx = pd.date_range("2025-01-01", periods=80, freq="s")
    data = rng.standard_normal((80, 3))
    data[60, 0] = 10.0  # injected anomaly
    return pd.DataFrame(data, index=idx, columns=["ch0", "ch1", "ch2"])


# ── LSTM AE ──────────────────────────────────────────────────────────────────


def test_lstm_train_and_score(config: dict, small_df: pd.DataFrame, tmp_path: Path) -> None:
    pytest.importorskip("tensorflow")
    cfg = dict(config)
    cfg["anomaly_detector"] = dict(cfg["anomaly_detector"])
    cfg["anomaly_detector"]["window_size"] = 10
    cfg["anomaly_detector"]["latent_dim"] = 8
    cfg["anomaly_detector"]["model_path"] = str(tmp_path / "lstm.keras")
    cfg["training"] = {
        "epochs": 2,
        "batch_size": 8,
        "validation_split": 0.0,
        "early_stopping_patience": 1,
    }

    det = AnomalyDetector(cfg, method="lstm")
    det.train(small_df)
    scores = det.score(small_df)
    assert scores.ndim == 1
    assert len(scores) == len(small_df) - 10 + 1
    assert scores.min() >= 0


def test_lstm_detect_returns_anomaly_results(
    config: dict, small_df: pd.DataFrame, tmp_path: Path
) -> None:
    pytest.importorskip("tensorflow")
    from ad_dss.common.schemas import AnomalyResult

    cfg = dict(config)
    cfg["anomaly_detector"] = dict(cfg["anomaly_detector"])
    cfg["anomaly_detector"]["window_size"] = 10
    cfg["anomaly_detector"]["latent_dim"] = 8
    cfg["anomaly_detector"]["model_path"] = str(tmp_path / "lstm.keras")
    cfg["training"] = {
        "epochs": 2,
        "batch_size": 8,
        "validation_split": 0.0,
        "early_stopping_patience": 1,
    }

    det = AnomalyDetector(cfg, method="lstm")
    det.train(small_df)
    results = det.detect(small_df, subsystem="EPS")
    assert len(results) > 0
    assert all(isinstance(r, AnomalyResult) for r in results)
    assert all(r.anomaly_flag in (0, 1) for r in results)
    assert all(r.subsystem == "EPS" for r in results)


def test_lstm_save_load(config: dict, small_df: pd.DataFrame, tmp_path: Path) -> None:
    pytest.importorskip("tensorflow")
    cfg = dict(config)
    cfg["anomaly_detector"] = dict(cfg["anomaly_detector"])
    cfg["anomaly_detector"]["window_size"] = 10
    cfg["anomaly_detector"]["latent_dim"] = 8
    cfg["anomaly_detector"]["model_path"] = str(tmp_path / "lstm.keras")
    cfg["training"] = {
        "epochs": 2,
        "batch_size": 8,
        "validation_split": 0.0,
        "early_stopping_patience": 1,
    }

    det = AnomalyDetector(cfg, method="lstm")
    det.train(small_df)
    scores_before = det.score(small_df)
    det.save()

    det2 = AnomalyDetector(cfg, method="lstm")
    det2.load()
    scores_after = det2.score(small_df)
    np.testing.assert_allclose(scores_before, scores_after, rtol=1e-4)


# ── Isolation Forest ──────────────────────────────────────────────────────────


def test_if_train_and_score(config: dict, small_df: pd.DataFrame) -> None:
    det = AnomalyDetector(config, method="isolation_forest")
    det.train(small_df)
    scores = det.score(small_df)
    assert scores.ndim == 1
    assert len(scores) == len(small_df)


def test_if_detect_flags_injected_anomaly(config: dict, small_df: pd.DataFrame) -> None:
    det = AnomalyDetector(config, method="isolation_forest")
    det.train(small_df)
    results = det.detect(small_df, subsystem="ADCS")
    flags = [r.anomaly_flag for r in results]
    # Injected anomaly at index 60 should be flagged
    assert 1 in flags


# ── Z-score ──────────────────────────────────────────────────────────────────


def test_zscore_score_shape(config: dict, small_df: pd.DataFrame) -> None:
    det = AnomalyDetector(config, method="zscore")
    scores = det.score(small_df)
    assert scores.ndim == 1
    assert len(scores) == len(small_df)


def test_zscore_detect_no_training_needed(config: dict, small_df: pd.DataFrame) -> None:
    det = AnomalyDetector(config, method="zscore")
    # No train() call — should work
    results = det.detect(small_df, subsystem="Thermal")
    assert len(results) == len(small_df)


# ── Factory ───────────────────────────────────────────────────────────────────


def test_build_detector_factory(config: dict) -> None:
    det = build_detector(config, method="zscore")
    assert isinstance(det, AnomalyDetector)
    assert det.method == "zscore"


def test_unknown_method_raises(config: dict, small_df: pd.DataFrame) -> None:
    det = AnomalyDetector(config, method="unknown")
    with pytest.raises(ValueError):
        det.train(small_df)
