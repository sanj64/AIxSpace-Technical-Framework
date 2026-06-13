"""Tests for decision/decision_logic.py."""

import pandas as pd
import pytest
import yaml

from ad_dss.common.schemas import Decision, MissionPhase, RiskResult
from ad_dss.decision.decision_logic import DecisionEngine


@pytest.fixture()
def config() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def _risk(level: str, subsystem: str = "EPS") -> RiskResult:
    return RiskResult(
        level=level, score=0.8 if level == "CRITICAL" else 0.4, reason="test", subsystem=subsystem, timestamp=pd.Timestamp("2025-01-01")
    )


def _phase(name: str = "Operations") -> MissionPhase:
    return MissionPhase(name=name, start_idx=0, end_idx=100)


def test_critical_triggers_safe_mode(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("CRITICAL"), _phase())
    assert decision.action == "SAFE_MODE"


def test_medium_eps_launch_aborts_payload(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("MEDIUM", "EPS"), _phase("Launch"))
    assert decision.action == "ABORT_PAYLOAD"


def test_medium_thermal_deployment_aborts(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("MEDIUM", "Thermal"), _phase("Deployment"))
    assert decision.action == "ABORT_PAYLOAD"


def test_medium_in_ops_notifies_ground(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("MEDIUM", "COM"), _phase("Operations"))
    assert decision.action == "NOTIFY_GROUND"


def test_low_risk_logs(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("LOW"), _phase())
    assert decision.action == "LOG"


def test_decide_returns_decision_schema(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("LOW"), _phase())
    assert isinstance(decision, Decision)
    assert decision.action in ("IGNORE", "LOG", "NOTIFY_GROUND", "SAFE_MODE", "ABORT_PAYLOAD")
    assert isinstance(decision.reason, str)
    assert isinstance(decision.timestamp, pd.Timestamp)


def test_rl_fallback_without_model(config: dict) -> None:
    engine = DecisionEngine(config, mode="rl")
    # No RL model loaded — should fall back gracefully
    decision = engine.decide_rl(0.9)
    assert isinstance(decision, Decision)
    assert decision.action in ("IGNORE", "LOG", "NOTIFY_GROUND", "SAFE_MODE", "ABORT_PAYLOAD")
