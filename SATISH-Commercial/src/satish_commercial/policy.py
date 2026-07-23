"""Deterministic advisory policy. There is no learned-policy path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import Action, RiskLevel, SystemMode

RULE_SET_VERSION = "commercial-advisory-rules:1.0.0"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: Action
    rule_ids: tuple[str, ...]
    trace: dict[str, Any]


def decide(*, mode: SystemMode, anomaly: bool, risk_level: RiskLevel) -> PolicyDecision:
    evaluated: list[dict[str, Any]] = []
    alternatives: list[dict[str, str]] = []

    degraded = mode is SystemMode.DEGRADED
    evaluated.append(
        {"rule_id": "SYS-001", "condition": "system_mode == DEGRADED", "value": degraded}
    )
    if degraded:
        alternatives.extend(
            [
                {"action": "NOMINAL", "rejected_because": "failed prerequisite"},
                {"action": "COOLDOWN", "rejected_because": "advisory autonomy withdrawn"},
                {"action": "SAFE_MODE", "rejected_because": "advisory autonomy withdrawn"},
            ]
        )
        return _decision(Action.ALERT_ONLY, ("SYS-001",), evaluated, alternatives, True)

    no_anomaly = not anomaly
    evaluated.append({"rule_id": "POL-001", "condition": "anomaly == false", "value": no_anomaly})
    if no_anomaly:
        return _decision(Action.NOMINAL, ("POL-001",), evaluated, alternatives, False)

    critical = risk_level is RiskLevel.CRITICAL
    evaluated.append(
        {"rule_id": "POL-002", "condition": "risk_level == CRITICAL", "value": critical}
    )
    if critical:
        alternatives.extend(
            [
                {"action": "COOLDOWN", "rejected_because": "risk met the critical threshold"},
                {"action": "ALERT_ONLY", "rejected_because": "risk met the critical threshold"},
            ]
        )
        return _decision(Action.SAFE_MODE, ("POL-002",), evaluated, alternatives, False)

    medium = risk_level is RiskLevel.MEDIUM
    evaluated.append({"rule_id": "POL-003", "condition": "risk_level == MEDIUM", "value": medium})
    if medium:
        alternatives.extend(
            [
                {"action": "SAFE_MODE", "rejected_because": "risk did not meet critical threshold"},
                {"action": "ALERT_ONLY", "rejected_because": "risk met the medium threshold"},
            ]
        )
        return _decision(Action.COOLDOWN, ("POL-003",), evaluated, alternatives, False)

    evaluated.append({"rule_id": "POL-004", "condition": "anomaly == true", "value": True})
    alternatives.extend(
        [
            {"action": "SAFE_MODE", "rejected_because": "risk below critical threshold"},
            {"action": "COOLDOWN", "rejected_because": "risk below medium threshold"},
        ]
    )
    return _decision(Action.ALERT_ONLY, ("POL-004",), evaluated, alternatives, False)


def _decision(
    action: Action,
    rule_ids: tuple[str, ...],
    evaluated: list[dict[str, Any]],
    alternatives: list[dict[str, str]],
    safety_override: bool,
) -> PolicyDecision:
    return PolicyDecision(
        action=action,
        rule_ids=rule_ids,
        trace={
            "rule_set_version": RULE_SET_VERSION,
            "evaluated_conditions": evaluated,
            "safety_override_applied": safety_override,
            "resulting_recommendation": action.value,
            "alternatives_considered": alternatives,
            "advisory_only": True,
            "command_execution": False,
        },
    )
