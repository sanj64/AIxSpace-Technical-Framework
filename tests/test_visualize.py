"""Tests for utils/visualize.py — all plots run headlessly."""

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from ad_dss.common.schemas import AnomalyResult, MissionPhase, RiskResult
from ad_dss.utils.visualize import (
    plot_anomaly_scores,
    plot_detector_comparison,
    plot_risk_timeline,
    plot_telemetry,
    save_figure,
)


def _make_df(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="s")
    rng = np.random.default_rng(0)
    return pd.DataFrame({"ch0": rng.standard_normal(n), "ch1": rng.standard_normal(n)}, index=idx)


def _anomalies(df: pd.DataFrame) -> list[AnomalyResult]:
    return [
        AnomalyResult(
            timestamp=df.index[i],
            subsystem="EPS",
            reconstruction_error=0.5,
            anomaly_flag=1,
            score=0.9,
        )
        for i in [10, 30, 50]
    ]


def _risks(df: pd.DataFrame) -> list[RiskResult]:
    levels = ["LOW", "MEDIUM", "CRITICAL"]
    return [
        RiskResult(level=levels[i % 3], score=0.1 + 0.4 * i, reason="test", subsystem="EPS", timestamp=df.index[i * 10])
        for i in range(3)
    ]


def test_plot_telemetry_returns_figure() -> None:
    df = _make_df()
    fig = plot_telemetry(df)
    assert isinstance(fig, Figure)


def test_plot_telemetry_with_anomalies() -> None:
    df = _make_df()
    fig = plot_telemetry(df, anomalies=_anomalies(df))
    assert isinstance(fig, Figure)


def test_plot_telemetry_with_phases() -> None:
    df = _make_df()
    phases = [MissionPhase("Launch", 0, 20), MissionPhase("Ops", 20, 60)]
    fig = plot_telemetry(df, phases=phases)
    assert isinstance(fig, Figure)


def test_plot_risk_timeline_returns_figure() -> None:
    df = _make_df()
    fig = plot_risk_timeline(_risks(df))
    assert isinstance(fig, Figure)


def test_plot_risk_timeline_empty() -> None:
    fig = plot_risk_timeline([])
    assert isinstance(fig, Figure)


def test_plot_anomaly_scores_returns_figure() -> None:
    scores = np.random.default_rng(0).random(50)
    fig = plot_anomaly_scores(scores, threshold=0.6)
    assert isinstance(fig, Figure)


def test_plot_anomaly_scores_no_threshold() -> None:
    scores = np.random.default_rng(0).random(50)
    fig = plot_anomaly_scores(scores)
    assert isinstance(fig, Figure)


def test_plot_detector_comparison_returns_figure() -> None:
    metrics = {
        "LSTM": {"Precision": 0.85, "Recall": 0.80, "F1": 0.82},
        "IsolationForest": {"Precision": 0.70, "Recall": 0.75, "F1": 0.72},
        "ZScore": {"Precision": 0.60, "Recall": 0.90, "F1": 0.72},
    }
    fig = plot_detector_comparison(metrics)
    assert isinstance(fig, Figure)


def test_save_figure(tmp_path) -> None:
    df = _make_df()
    fig = plot_telemetry(df)
    out = str(tmp_path / "test.png")
    save_figure(fig, out)
    import os
    assert os.path.exists(out)
