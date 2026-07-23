"""Transparent, deterministic risk arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import RiskLevel


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    level: RiskLevel
    value: float
    decomposition: dict[str, Any]


def calculate_risk(
    *,
    anomaly: bool,
    consecutive_anomalies: int,
    criticality_weight: float,
    mission_phase: str,
    mission_phase_weight: float,
    medium_threshold: float,
    critical_threshold: float,
    persistence_horizon: int,
) -> RiskAssessment:
    if persistence_horizon < 1:
        raise ValueError("persistence_horizon must be positive")
    if not anomaly:
        return RiskAssessment(
            level=RiskLevel.NONE,
            value=0.0,
            decomposition={
                "anomaly_term": 0.0,
                "persistence_count": 0,
                "persistence_horizon": persistence_horizon,
                "persistence_term": 0.0,
                "subsystem_criticality": criticality_weight,
                "mission_phase": mission_phase,
                "mission_phase_weight": mission_phase_weight,
                "risk_value": 0.0,
                "arithmetic": "0 (no anomaly)",
                "thresholds": {"medium": medium_threshold, "critical": critical_threshold},
                "factor_that_can_lower_level": "no anomaly signal",
            },
        )
    persistence_term = min(max(consecutive_anomalies, 1) / persistence_horizon, 1.0)
    anomaly_term = 0.5 + (0.5 * persistence_term)
    value = anomaly_term * criticality_weight * mission_phase_weight
    if value >= critical_threshold:
        level = RiskLevel.CRITICAL
        lower_boundary = critical_threshold
    elif value >= medium_threshold:
        level = RiskLevel.MEDIUM
        lower_boundary = medium_threshold
    else:
        level = RiskLevel.LOW
        lower_boundary = medium_threshold
    return RiskAssessment(
        level=level,
        value=value,
        decomposition={
            "anomaly_term": anomaly_term,
            "persistence_count": consecutive_anomalies,
            "persistence_horizon": persistence_horizon,
            "persistence_term": persistence_term,
            "subsystem_criticality": criticality_weight,
            "mission_phase": mission_phase,
            "mission_phase_weight": mission_phase_weight,
            "risk_value": value,
            "arithmetic": (
                f"({anomaly_term:.6g}) x ({criticality_weight:.6g}) x "
                f"({mission_phase_weight:.6g}) = {value:.6g}"
            ),
            "thresholds": {"medium": medium_threshold, "critical": critical_threshold},
            "factor_that_changed_level": "persistence, criticality, and mission-phase product",
            "factor_that_can_lower_level": (
                f"a valid factor change that makes risk < {lower_boundary:.6g}; "
                "configuration changes require independent approval and regression evidence"
            ),
        },
    )
