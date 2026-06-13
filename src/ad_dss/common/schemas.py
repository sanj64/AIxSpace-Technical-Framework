from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class TelemetryFrame:
    df: "pd.DataFrame"
    subsystems: list[str]
    source: str = "unknown"


@dataclass
class AnomalyResult:
    timestamp: "pd.Timestamp"
    subsystem: str
    reconstruction_error: float
    anomaly_flag: int  # 0 or 1
    score: float  # normalised 0..1


@dataclass
class RiskResult:
    level: Literal["LOW", "MEDIUM", "CRITICAL"]
    score: float  # 0..1
    reason: str
    subsystem: str
    timestamp: "pd.Timestamp"


@dataclass
class Decision:
    action: Literal["IGNORE", "LOG", "NOTIFY_GROUND", "SAFE_MODE", "ABORT_PAYLOAD"]
    reason: str
    timestamp: "pd.Timestamp"


@dataclass
class BackupAction:
    component: str
    fallback_component: str
    activated: bool
    reason: str
    timestamp: "pd.Timestamp"


@dataclass
class MissionPhase:
    name: str
    start_idx: int
    end_idx: int


@dataclass
class MissionEvent:
    step: int
    timestamp: "pd.Timestamp"
    phase: MissionPhase
    telemetry_snapshot: dict
    anomaly_flags: list[AnomalyResult] = field(default_factory=list)
    risk: RiskResult | None = None
    decision: Decision | None = None
    backups: list[BackupAction] = field(default_factory=list)
