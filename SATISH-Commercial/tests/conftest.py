from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from satish_commercial.configuration import FIXED_RULES, load_config
from satish_commercial.signing import sign_mapping


def config_mapping(detector: str = "zscore") -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "schema_version": "1.0.0",
        "pack_id": "test-pack",
        "customer_id": "test-customer",
        "detector": detector,
        "timestamp_column": "timestamp",
        "feature_columns": ["temperature", "voltage"],
        "subsystem_lookup": {"temperature": "THERMAL", "voltage": "POWER"},
        "physical_bounds": {
            "temperature": {"min": -100.0, "max": 200.0},
            "voltage": {"min": 0.0, "max": 100.0},
        },
        "detector_settings": {
            "label_column": "anomaly_label",
            "window": 10,
            "calibration_quantile": 0.95,
            "minimum_z_threshold": 2.5,
            "estimators": 40,
            "seed": 7,
            "max_gap_seconds": 120,
            "persistence_horizon": 3,
        },
        "risk_thresholds": {"medium": 1.0, "critical": 1.5},
        "criticality_weights": {"THERMAL": 1.4, "POWER": 1.2, "DEFAULT": 1.0},
        "mission_phase_weights": {"DEFAULT": 1.0, "ROUTINE": 1.0},
        "deterministic_rules": [dict(item) for item in FIXED_RULES],
        "branding": {"product_name": "Test SATISH"},
        "author": "author@example.test",
        "independent_approver": "approver@example.test",
        "effective_at": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        "second_person_review": False,
    }


@pytest.fixture
def signing_material(tmp_path: Path) -> tuple[Ed25519PrivateKey, Path]:
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "public.pem"
    public_path.write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private, public_path


@pytest.fixture
def signed_config(tmp_path: Path, signing_material: tuple[Ed25519PrivateKey, Path]):
    private, public_path = signing_material
    mapping = sign_mapping(config_mapping(), private)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return load_config(path, public_path), path, private, public_path
