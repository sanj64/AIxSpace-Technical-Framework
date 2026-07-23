"""Versioned commercial interfaces and canonical serialization.

These records intentionally contain no command, actuator, or command-acknowledgement
field. Recommendations are advisory records that require human disposition.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Action(StrEnum):
    NOMINAL = "NOMINAL"
    COOLDOWN = "COOLDOWN"
    SAFE_MODE = "SAFE_MODE"
    ALERT_ONLY = "ALERT_ONLY"


class SystemMode(StrEnum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"


class Disposition(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class RiskLevel(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    CRITICAL = "CRITICAL"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            item.name: _json_value(getattr(value, item.name)) for item in dataclasses.fields(value)
        }
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def to_dict(value: Any) -> dict[str, Any]:
    converted = _json_value(value)
    if not isinstance(converted, dict):
        raise TypeError("top-level contract value must serialize to an object")
    return converted


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True, slots=True)
class RiskPacketV1:
    schema_version: str
    packet_id: str
    run_id: str
    event_id: str
    timestamp: str
    subsystem: str
    detector_identity: str
    artifact_hash: str
    config_hash: str
    feature_schema_hash: str
    score: float | None
    threshold: float | None
    margin: float | None
    anomaly: bool
    data_quality_flags: tuple[str, ...]
    system_mode: SystemMode


@dataclass(frozen=True, slots=True)
class ExplanationPacketV1:
    schema_version: str
    explanation_id: str
    risk_packet_id: str
    detector_evidence: dict[str, Any]
    reference_baseline: dict[str, Any]
    ranked_feature_contributions: tuple[dict[str, Any], ...]
    risk_factor_decomposition: dict[str, Any]
    deterministic_policy_trace: dict[str, Any]
    feasible_counterfactual: dict[str, Any]
    limitations: tuple[str, ...]
    explanation_implementation_version: str


@dataclass(frozen=True, slots=True)
class RecommendationRecordV1:
    schema_version: str
    recommendation_id: str
    risk_packet_id: str
    explanation_id: str
    action: Action
    rule_set_version: str
    rule_ids: tuple[str, ...]
    disposition: Disposition = Disposition.PENDING
    operator_identity: str | None = None
    disposition_timestamp: str | None = None
    reason_code: str | None = None
    rationale: str | None = None
    second_reviewer_identity: str | None = None

    def disposed(
        self,
        disposition: Disposition,
        operator_identity: str,
        reason_code: str,
        rationale: str,
        *,
        second_reviewer_identity: str | None = None,
    ) -> RecommendationRecordV1:
        if disposition is Disposition.PENDING:
            raise ValueError("a disposition action cannot set a recommendation back to PENDING")
        if not operator_identity.strip():
            raise ValueError("a named operator identity is required")
        if not reason_code.strip() or not rationale.strip():
            raise ValueError("reason code and rationale are required")
        if self.action is Action.SAFE_MODE and len(rationale.strip()) < 12:
            raise ValueError("SAFE_MODE dispositions require a substantive rationale")
        return dataclasses.replace(
            self,
            disposition=disposition,
            operator_identity=operator_identity.strip(),
            disposition_timestamp=utc_now(),
            reason_code=reason_code.strip(),
            rationale=rationale.strip(),
            second_reviewer_identity=(
                second_reviewer_identity.strip() if second_reviewer_identity else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ConfigPackV1:
    schema_version: str
    pack_id: str
    customer_id: str
    detector: str
    timestamp_column: str
    feature_columns: tuple[str, ...]
    subsystem_lookup: dict[str, str]
    physical_bounds: dict[str, dict[str, float]]
    detector_settings: dict[str, Any]
    risk_thresholds: dict[str, float]
    criticality_weights: dict[str, float]
    mission_phase_weights: dict[str, float]
    deterministic_rules: tuple[dict[str, Any], ...]
    branding: dict[str, str]
    author: str
    independent_approver: str
    effective_at: str
    expires_at: str
    second_person_review: bool
    pack_hash: str
    signing_algorithm: str
    signature: str


@dataclass(frozen=True, slots=True)
class LiveTelemetrySampleV1:
    schema_version: str
    sequence: int
    timestamp: str
    source: str
    mission_phase: str
    channel_order: tuple[str, ...]
    channel_values: dict[str, float | None]


@dataclass(frozen=True, slots=True)
class LiveMonitorUpdateV1:
    schema_version: str
    session_id: str
    sequence: int
    emitted_at: str
    stream_health: dict[str, Any]
    sample: LiveTelemetrySampleV1
    risk_packet: RiskPacketV1
    explanation: ExplanationPacketV1
    recommendation: RecommendationRecordV1
    audit_entry_hash: str


@dataclass(frozen=True, slots=True)
class LiveControlV1:
    schema_version: str
    session_id: str
    action: str
    scenario: str | None = None
    speed: float | None = None


@dataclass(frozen=True, slots=True)
class RunManifestV1:
    schema_version: str
    run_id: str
    created_at: str
    dataset_ids: tuple[dict[str, Any], ...]
    split_boundaries: dict[str, Any]
    code_commit: str
    environment: dict[str, str]
    sbom_hash: str
    artifact_hash: str
    config_pack_hash: str
    feature_schema_hash: str
    seed: int
    metrics: dict[str, Any]
    generated_output_hashes: dict[str, str] = field(default_factory=dict)


def require_v1(version: str) -> None:
    try:
        major = int(version.split(".", maxsplit=1)[0])
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"invalid schema version: {version!r}") from exc
    if major != 1:
        raise ValueError(f"unsupported schema major version {major}; only major 1 is accepted")
