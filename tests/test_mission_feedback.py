"""Tests for feedback/mission_feedback.py."""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from ad_dss.common.schemas import AnomalyResult
from ad_dss.feedback.mission_feedback import MissionFeedback


def _make_run(
    n_anomalies: int = 10,
    flag_rate: float = 0.05,
    score_mean: float = 0.02,
    dataset: str = "test",
) -> dict:
    n = int(n_anomalies / max(flag_rate, 1e-6))
    ts = pd.Timestamp("2025-01-01")
    anomalies = [
        AnomalyResult(
            timestamp=ts,
            subsystem="EPS",
            reconstruction_error=float(score_mean + 0.001 * i),
            anomaly_flag=1 if i < n_anomalies else 0,
            score=float(score_mean),
        )
        for i in range(min(n, 200))
    ]
    df = pd.DataFrame({"EPS_v": np.ones(min(n, 200))})
    return {"anomalies": anomalies, "telemetry_df": df, "dataset": dataset, "method": "zscore"}


def test_record_stores_history() -> None:
    fb = MissionFeedback()
    fb.record(_make_run())
    assert len(fb._history) == 1
    assert "flag_rate" in fb._history[0]


def test_analyse_not_enough_history() -> None:
    fb = MissionFeedback()
    result = fb.analyse()
    assert result["drift_detected"] is False
    assert "Not enough" in result["warnings"][0]


def test_analyse_no_drift_stable_runs() -> None:
    fb = MissionFeedback()
    for _ in range(4):
        fb.record(_make_run(n_anomalies=5, flag_rate=0.05, score_mean=0.02))
    result = fb.analyse()
    assert result["drift_detected"] is False
    assert result["n_runs_analysed"] == 4


def test_analyse_detects_flagrate_drift() -> None:
    fb = MissionFeedback(drift_z_threshold=1.5)
    # Slightly varying baseline so std > 0
    for rate in [0.01, 0.012, 0.008, 0.011]:
        fb.record(_make_run(n_anomalies=int(200 * rate), flag_rate=rate, score_mean=0.01))
    # Inject a run with massively elevated flag rate
    fb.record(_make_run(n_anomalies=160, flag_rate=0.80, score_mean=0.5))
    result = fb.analyse()
    assert result["drift_detected"] is True
    assert any("drift" in w.lower() for w in result["warnings"])


def test_analyse_returns_threshold_suggestion() -> None:
    fb = MissionFeedback()
    for _ in range(3):
        fb.record(_make_run(score_mean=0.05))
    result = fb.analyse()
    assert result["suggested_p95_threshold"] is not None
    assert isinstance(result["suggested_p95_threshold"], float)


def test_window_limits_history() -> None:
    fb = MissionFeedback(window=3)
    for i in range(6):
        fb.record(_make_run(dataset=f"run_{i}"))
    assert len(fb._history) == 3
    assert fb._history[-1]["dataset"] == "run_5"


def test_clear_history() -> None:
    fb = MissionFeedback()
    fb.record(_make_run())
    fb.clear_history()
    assert len(fb._history) == 0


def test_write_threshold_no_history(tmp_path: Path) -> None:
    cfg = {"anomaly_detector": {"thresholds": {"default": 0.5}}, "seed": 42}
    cfg_file = tmp_path / "settings.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg))
    fb = MissionFeedback(config_path=cfg_file)
    written = fb.write_threshold_suggestion()
    assert written is False


def test_write_threshold_updates_yaml(tmp_path: Path) -> None:
    cfg = {"anomaly_detector": {"thresholds": {"default": 0.5}}, "seed": 42}
    cfg_file = tmp_path / "settings.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg))
    fb = MissionFeedback(config_path=cfg_file)
    for _ in range(3):
        fb.record(_make_run(score_mean=0.03))
    written = fb.write_threshold_suggestion(subsystem="EPS")
    assert written is True
    updated = yaml.safe_load(cfg_file.read_text())
    assert "EPS" in updated["anomaly_detector"]["thresholds"]
