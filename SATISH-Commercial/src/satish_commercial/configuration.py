"""Loading and validation for signed, data-only customer configuration packs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .contracts import ConfigPackV1, require_v1
from .signing import load_private_key, load_public_key, sign_mapping, verify_mapping

ALLOWED_DETECTORS = {"zscore", "isolation_forest"}
FIXED_RULES = (
    {"rule_id": "SYS-001", "when": "system_mode == DEGRADED", "action": "ALERT_ONLY"},
    {"rule_id": "POL-001", "when": "anomaly == false", "action": "NOMINAL"},
    {"rule_id": "POL-002", "when": "risk_level == CRITICAL", "action": "SAFE_MODE"},
    {"rule_id": "POL-003", "when": "risk_level == MEDIUM", "action": "COOLDOWN"},
    {"rule_id": "POL-004", "when": "anomaly == true", "action": "ALERT_ONLY"},
)


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def read_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() in {".yaml", ".yml"}:
            value = yaml.safe_load(handle)
        else:
            value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("configuration pack must be a JSON/YAML object")
    return value


def sign_config(source: Path, private_key_path: Path, output: Path) -> None:
    mapping = read_mapping(source)
    validate_unsigned_config(mapping)
    signed = sign_mapping(mapping, load_private_key(private_key_path))
    output.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_unsigned_config(mapping: dict[str, Any]) -> None:
    require_v1(str(mapping.get("schema_version", "")))
    required = {
        "pack_id",
        "customer_id",
        "detector",
        "timestamp_column",
        "feature_columns",
        "subsystem_lookup",
        "physical_bounds",
        "detector_settings",
        "risk_thresholds",
        "criticality_weights",
        "mission_phase_weights",
        "deterministic_rules",
        "branding",
        "author",
        "independent_approver",
        "effective_at",
        "expires_at",
        "second_person_review",
    }
    missing = sorted(required - mapping.keys())
    if missing:
        raise ValueError(f"missing configuration fields: {', '.join(missing)}")
    permitted = required | {"schema_version", "pack_hash", "signing_algorithm", "signature"}
    unknown = sorted(mapping.keys() - permitted)
    if unknown:
        raise ValueError(f"unknown configuration fields are prohibited: {', '.join(unknown)}")
    if mapping["detector"] not in ALLOWED_DETECTORS:
        raise ValueError("production detector must be zscore or isolation_forest")
    if not str(mapping["detector_settings"].get("label_column", "")).strip():
        raise ValueError("detector_settings.label_column is required for normal-only training")
    if str(mapping["author"]).strip() == str(mapping["independent_approver"]).strip():
        raise ValueError("configuration authors cannot approve their own packs")
    features = tuple(str(item) for item in mapping["feature_columns"])
    if not features or len(features) != len(set(features)):
        raise ValueError("feature_columns must contain unique values")
    if set(mapping["subsystem_lookup"]) != set(features):
        raise ValueError("subsystem_lookup must map every feature and no unknown feature")
    if set(mapping["physical_bounds"]) != set(features):
        raise ValueError("physical_bounds must define every feature and no unknown feature")
    for feature, bounds in mapping["physical_bounds"].items():
        if not isinstance(bounds, dict) or float(bounds["min"]) >= float(bounds["max"]):
            raise ValueError(f"invalid physical bounds for {feature}")
    risk = mapping["risk_thresholds"]
    if not (0 <= float(risk["medium"]) < float(risk["critical"])):
        raise ValueError("risk thresholds must satisfy 0 <= medium < critical")
    if any(float(value) <= 0 for value in mapping["criticality_weights"].values()):
        raise ValueError("criticality weights must be positive")
    if any(float(value) <= 0 for value in mapping["mission_phase_weights"].values()):
        raise ValueError("mission-phase weights must be positive")
    if tuple(mapping["deterministic_rules"]) != FIXED_RULES:
        raise ValueError("the deterministic safety rule set cannot be customized in v0.9")
    effective = _parse_time(str(mapping["effective_at"]), "effective_at")
    expires = _parse_time(str(mapping["expires_at"]), "expires_at")
    if effective >= expires:
        raise ValueError("effective_at must be earlier than expires_at")


def load_config(path: Path, public_key_path: Path, *, at: datetime | None = None) -> ConfigPackV1:
    mapping = read_mapping(path)
    validate_unsigned_config(mapping)
    verify_mapping(mapping, load_public_key(public_key_path))
    moment = (at or datetime.now(UTC)).astimezone(UTC)
    effective = _parse_time(str(mapping["effective_at"]), "effective_at")
    expires = _parse_time(str(mapping["expires_at"]), "expires_at")
    if moment < effective:
        raise ValueError("configuration pack is not yet effective")
    if moment >= expires:
        raise ValueError("configuration pack has expired")
    return ConfigPackV1(
        schema_version=str(mapping["schema_version"]),
        pack_id=str(mapping["pack_id"]),
        customer_id=str(mapping["customer_id"]),
        detector=str(mapping["detector"]),
        timestamp_column=str(mapping["timestamp_column"]),
        feature_columns=tuple(str(item) for item in mapping["feature_columns"]),
        subsystem_lookup={str(k): str(v) for k, v in mapping["subsystem_lookup"].items()},
        physical_bounds={
            str(k): {"min": float(v["min"]), "max": float(v["max"])}
            for k, v in mapping["physical_bounds"].items()
        },
        detector_settings=dict(mapping["detector_settings"]),
        risk_thresholds={str(k): float(v) for k, v in mapping["risk_thresholds"].items()},
        criticality_weights={str(k): float(v) for k, v in mapping["criticality_weights"].items()},
        mission_phase_weights={
            str(k): float(v) for k, v in mapping["mission_phase_weights"].items()
        },
        deterministic_rules=tuple(dict(item) for item in mapping["deterministic_rules"]),
        branding={str(k): str(v) for k, v in mapping["branding"].items()},
        author=str(mapping["author"]),
        independent_approver=str(mapping["independent_approver"]),
        effective_at=str(mapping["effective_at"]),
        expires_at=str(mapping["expires_at"]),
        second_person_review=bool(mapping["second_person_review"]),
        pack_hash=str(mapping["pack_hash"]),
        signing_algorithm=str(mapping["signing_algorithm"]),
        signature=str(mapping["signature"]),
    )
