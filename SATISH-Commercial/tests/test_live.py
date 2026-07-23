from __future__ import annotations

import json

import numpy as np
import pandas as pd

from satish_commercial.audit import AuditLog, verify_audit
from satish_commercial.contracts import SystemMode, to_dict
from satish_commercial.detectors import CausalZScoreDetector, feature_schema_hash
from satish_commercial.live import SyntheticTelemetryGenerator, recover_interrupted_sessions
from satish_commercial.processing import AdvisoryProcessor
from satish_commercial.quality import assess_sample
from satish_commercial.signing import load_public_key


def _processor(config):
    train = np.column_stack([np.linspace(19.5, 20.5, 30), np.linspace(27.0, 28.0, 30)])
    calibration = np.column_stack([np.linspace(19.8, 20.2, 12), np.linspace(27.3, 27.7, 12)])
    detector = CausalZScoreDetector(
        config.feature_columns,
        window=10,
        calibration_quantile=0.9,
        minimum_threshold=2.5,
    )
    detector.fit(train)
    detector.calibrate(calibration)
    return AdvisoryProcessor(
        config=config,
        detector=detector,
        artifact_hash="a" * 64,
        feature_schema_hash=feature_schema_hash(config.feature_columns),
        run_id="live-test-run",
        evidence_scope="test live stream",
    ), detector


def test_anomalous_sample_does_not_contaminate_reference(signed_config) -> None:
    config, *_ = signed_config
    processor, detector = _processor(config)
    before = [item.copy() for item in detector._history]
    result = processor.process(
        pd.Series({"timestamp": "2026-01-01T00:00:00Z", "temperature": 150.0, "voltage": 27.5}),
        index=1,
        mode=SystemMode.NORMAL,
    )
    assert result.risk_packet.anomaly is True
    assert all(
        np.array_equal(left, right) for left, right in zip(before, detector._history, strict=True)
    )
    assert "do not update the detector reference" in " ".join(result.explanation.limitations)


def test_nominal_sample_updates_reference(signed_config) -> None:
    config, *_ = signed_config
    processor, detector = _processor(config)
    previous_last = detector._history[-1].copy()
    result = processor.process(
        pd.Series({"timestamp": "2026-01-01T00:00:00Z", "temperature": 20.0, "voltage": 27.5}),
        index=1,
        mode=SystemMode.NORMAL,
    )
    assert result.risk_packet.anomaly is False
    assert not np.array_equal(previous_last, detector._history[-1])


def test_live_quality_failures_force_degraded_alert_only(signed_config) -> None:
    config, *_ = signed_config
    processor, _ = _processor(config)
    quality = assess_sample(
        timestamp="2026-01-01T00:00:00Z",
        channel_order=("voltage", "temperature"),
        channel_values={"temperature": float("nan"), "voltage": 27.5},
        mission_phase="ROUTINE",
        config=config,
        previous_timestamp=None,
    )
    result = processor.process(
        quality.row,
        index=1,
        mode=quality.mode,
        quality_flags=quality.flags,
    )
    assert result.risk_packet.system_mode is SystemMode.DEGRADED
    assert result.recommendation.action.value == "ALERT_ONLY"
    assert "schema_order_mismatch" in result.risk_packet.data_quality_flags
    assert "nonfinite_value:temperature" in result.risk_packet.data_quality_flags


def test_synthetic_scenarios_are_deterministic_and_explicit() -> None:
    first = SyntheticTelemetryGenerator(("battery_temperature_c", "bus_voltage_v"), seed=42)
    second = SyntheticTelemetryGenerator(("battery_temperature_c", "bus_voltage_v"), seed=42)
    sample_a = first.next_sample(1)
    sample_b = second.next_sample(1)
    assert sample_a.channel_values == sample_b.channel_values
    assert sample_a.source == "seeded_synthetic_local"
    first.select("thermal_rise")
    first.inject()
    injected = first.next_sample(2)
    assert injected.channel_values["battery_temperature_c"] == 27.0


def test_live_records_contain_no_command_or_actuation_fields(signed_config) -> None:
    config, *_ = signed_config
    processor, _ = _processor(config)
    result = processor.process(
        pd.Series({"timestamp": "2026-01-01T00:00:00Z", "temperature": 20.0, "voltage": 27.5}),
        index=1,
        mode=SystemMode.NORMAL,
    )
    serialized = json.dumps(
        {
            "risk": to_dict(result.risk_packet),
            "explanation": to_dict(result.explanation),
            "recommendation": to_dict(result.recommendation),
        }
    ).lower()
    assert '"command"' not in serialized
    assert '"actuation"' not in serialized


def test_interrupted_session_is_closed_with_atomic_manifest(tmp_path, signed_config) -> None:
    _, _, private_key, public_path = signed_config
    session = tmp_path / "live-recovery-test"
    session.mkdir()
    AuditLog(session / "audit.jsonl", private_key).append(
        "LIVE_SESSION_STARTED", {"session_id": session.name}
    )
    (session / "telemetry.jsonl").write_text('{"sequence":1}\n', encoding="utf-8")
    checkpoint = {
        "schema_version": "1.0.0",
        "session_id": session.name,
        "status": "ACTIVE",
        "sample_count": 1,
        "generated_output_hashes": {},
    }
    (session / "live-session.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    recovered = recover_interrupted_sessions(tmp_path, private_key)

    manifest = json.loads((session / "run-manifest.json").read_text(encoding="utf-8"))
    assert recovered == [session.name]
    assert manifest["status"] == "INTERRUPTED"
    assert "telemetry.jsonl" in manifest["generated_output_hashes"]
    assert verify_audit(session / "audit.jsonl", load_public_key(public_path)) == 2
    assert not list(session.glob("*.tmp"))
