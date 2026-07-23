from __future__ import annotations

import pytest

from satish_commercial.contracts import (
    Action,
    Disposition,
    RecommendationRecordV1,
    RiskLevel,
    SystemMode,
    require_v1,
)
from satish_commercial.policy import decide


def test_action_vocabulary_is_fixed() -> None:
    assert {item.value for item in Action} == {"NOMINAL", "COOLDOWN", "SAFE_MODE", "ALERT_ONLY"}


@pytest.mark.parametrize(
    ("mode", "anomaly", "risk", "expected"),
    [
        (SystemMode.DEGRADED, True, RiskLevel.CRITICAL, Action.ALERT_ONLY),
        (SystemMode.NORMAL, False, RiskLevel.NONE, Action.NOMINAL),
        (SystemMode.NORMAL, True, RiskLevel.LOW, Action.ALERT_ONLY),
        (SystemMode.NORMAL, True, RiskLevel.MEDIUM, Action.COOLDOWN),
        (SystemMode.NORMAL, True, RiskLevel.CRITICAL, Action.SAFE_MODE),
    ],
)
def test_policy_has_no_bypass(mode, anomaly, risk, expected) -> None:
    decision = decide(mode=mode, anomaly=anomaly, risk_level=risk)
    assert decision.action is expected
    assert decision.trace["command_execution"] is False
    assert decision.trace["advisory_only"] is True


def test_safe_mode_disposition_requires_identity_and_rationale() -> None:
    record = RecommendationRecordV1(
        "1.0.0", "rec", "risk", "exp", Action.SAFE_MODE, "rules:1", ("POL-002",)
    )
    with pytest.raises(ValueError):
        record.disposed(Disposition.ACCEPTED, "operator", "CONFIRMED", "short")
    updated = record.disposed(
        Disposition.REJECTED,
        "operator@example.test",
        "KNOWN_EVENT",
        "Known nominal eclipse transition",
    )
    assert updated.disposition is Disposition.REJECTED
    assert updated.operator_identity == "operator@example.test"


def test_unknown_schema_major_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported schema major"):
        require_v1("2.0.0")
