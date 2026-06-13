"""Tests for decision/backup_strategy.py."""

import pandas as pd
import pytest
import yaml

from ad_dss.common.schemas import BackupAction, Decision, RiskResult
from ad_dss.decision.backup_strategy import BackupStrategyManager


@pytest.fixture()
def config() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def _risk(level: str, subsystem: str) -> RiskResult:
    return RiskResult(
        level=level,
        score=0.9,
        reason="test",
        subsystem=subsystem,
        timestamp=pd.Timestamp("2025-01-01"),
    )


def _decision(action: str = "SAFE_MODE") -> Decision:
    return Decision(action=action, reason="test", timestamp=pd.Timestamp("2025-01-01"))


def test_critical_eps_activates_backup(config: dict) -> None:
    mgr = BackupStrategyManager(config)
    actions = mgr.evaluate(_decision(), _risk("CRITICAL", "EPS"))
    assert len(actions) == 1
    assert actions[0].activated is True
    assert "backup_battery" in actions[0].fallback_component


def test_medium_adcs_activates_backup(config: dict) -> None:
    mgr = BackupStrategyManager(config)
    actions = mgr.evaluate(_decision(), _risk("MEDIUM", "ADCS"))
    assert len(actions) == 1
    assert "magnetometer" in actions[0].fallback_component


def test_low_risk_no_backup(config: dict) -> None:
    mgr = BackupStrategyManager(config)
    actions = mgr.evaluate(_decision(), _risk("LOW", "EPS"))
    assert actions == []


def test_unknown_subsystem_no_backup(config: dict) -> None:
    mgr = BackupStrategyManager(config)
    actions = mgr.evaluate(_decision(), _risk("CRITICAL", "UNKNOWN_SYS"))
    assert actions == []


def test_backup_action_schema(config: dict) -> None:
    mgr = BackupStrategyManager(config)
    actions = mgr.evaluate(_decision(), _risk("CRITICAL", "Thermal"))
    assert isinstance(actions[0], BackupAction)
    assert actions[0].component != ""
    assert isinstance(actions[0].timestamp, pd.Timestamp)


def test_evaluate_all(config: dict) -> None:
    mgr = BackupStrategyManager(config)
    pairs = [
        (_decision(), _risk("CRITICAL", "EPS")),
        (_decision(), _risk("LOW", "COM")),
        (_decision(), _risk("MEDIUM", "ADCS")),
    ]
    all_actions = mgr.evaluate_all(pairs)
    # EPS critical + ADCS medium should each activate
    assert len(all_actions) == 2
