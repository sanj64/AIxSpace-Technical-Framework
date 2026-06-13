"""Tests for models/risk_predictor.py."""

import pandas as pd
import pytest
import yaml

from ad_dss.common.schemas import AnomalyResult, MissionPhase, RiskResult
from ad_dss.models.risk_predictor import RiskPredictor, aggregate_risk


@pytest.fixture()
def config() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def ops_phase() -> MissionPhase:
    return MissionPhase(name="Operations", start_idx=0, end_idx=100)


@pytest.fixture()
def deploy_phase() -> MissionPhase:
    return MissionPhase(name="Deployment", start_idx=0, end_idx=50)


def _make_anomaly(subsystem: str, flag: int, score: float = 0.5) -> AnomalyResult:
    return AnomalyResult(
        timestamp=pd.Timestamp("2025-01-01"),
        subsystem=subsystem,
        reconstruction_error=score,
        anomaly_flag=flag,
        score=score,
    )


def test_predict_low_for_zero_anomaly(config: dict, ops_phase: MissionPhase) -> None:
    rp = RiskPredictor(config)
    anomalies = [_make_anomaly("EPS", flag=0, score=0.0)]
    results = rp.predict(anomalies, ops_phase)
    assert len(results) == 1
    assert results[0].level == "LOW"


def test_predict_critical_for_persistent_anomalies(config: dict, ops_phase: MissionPhase) -> None:
    rp = RiskPredictor(config)
    # Feed 5 consecutive anomalies to fill the persistence window
    for _ in range(5):
        rp.predict([_make_anomaly("EPS", flag=1, score=1.0)], ops_phase)
    results = rp.predict([_make_anomaly("EPS", flag=1, score=1.0)], ops_phase)
    assert results[0].level in ("MEDIUM", "CRITICAL")


def test_predict_includes_subsystem(config: dict, ops_phase: MissionPhase) -> None:
    rp = RiskPredictor(config)
    results = rp.predict([_make_anomaly("Thermal", flag=1, score=0.8)], ops_phase)
    assert results[0].subsystem == "Thermal"


def test_predict_reason_contains_phase(config: dict, deploy_phase: MissionPhase) -> None:
    rp = RiskPredictor(config)
    for _ in range(3):
        rp.predict([_make_anomaly("ADCS", flag=1, score=0.9)], deploy_phase)
    results = rp.predict([_make_anomaly("ADCS", flag=1, score=0.9)], deploy_phase)
    assert "Deployment" in results[0].reason


def test_multiple_subsystems(config: dict, ops_phase: MissionPhase) -> None:
    rp = RiskPredictor(config)
    anomalies = [
        _make_anomaly("EPS", flag=1, score=0.8),
        _make_anomaly("Thermal", flag=0, score=0.0),
    ]
    results = rp.predict(anomalies, ops_phase)
    subs = {r.subsystem for r in results}
    assert "EPS" in subs
    assert "Thermal" in subs


def test_reset_history(config: dict, ops_phase: MissionPhase) -> None:
    rp = RiskPredictor(config)
    for _ in range(5):
        rp.predict([_make_anomaly("EPS", flag=1, score=1.0)], ops_phase)
    rp.reset_history()
    results = rp.predict([_make_anomaly("EPS", flag=0, score=0.0)], ops_phase)
    assert results[0].level == "LOW"


def test_aggregate_risk_returns_highest(config: dict) -> None:
    ts = pd.Timestamp("2025-01-01")
    risks = [
        RiskResult(level="LOW", score=0.1, reason="", subsystem="A", timestamp=ts),
        RiskResult(level="CRITICAL", score=0.9, reason="", subsystem="B", timestamp=ts),
        RiskResult(level="MEDIUM", score=0.5, reason="", subsystem="C", timestamp=ts),
    ]
    top = aggregate_risk(risks)
    assert top is not None
    assert top.level == "CRITICAL"


def test_aggregate_risk_empty_returns_none(config: dict) -> None:
    assert aggregate_risk([]) is None


def test_predict_empty_anomalies(config: dict, ops_phase: MissionPhase) -> None:
    rp = RiskPredictor(config)
    results = rp.predict([], ops_phase)
    assert results == []
