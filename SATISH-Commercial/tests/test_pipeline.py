from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import numpy as np
import pandas as pd
import pytest

from satish_commercial.audit import verify_audit
from satish_commercial.contracts import Action, Disposition, SystemMode
from satish_commercial.pipeline import file_sha256, record_disposition, run_replay
from satish_commercial.signing import load_public_key


def telemetry(rows: int = 150) -> pd.DataFrame:
    rng = np.random.default_rng(10)
    result = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="60s", tz="UTC"),
            "temperature": 20 + rng.normal(0, 0.2, rows),
            "voltage": 28 + rng.normal(0, 0.1, rows),
            "anomaly_label": np.zeros(rows, dtype=int),
            "mission_phase": "ROUTINE",
            "rare_nominal": False,
        }
    )
    result.loc[130:134, "temperature"] = 35
    result.loc[130:134, "anomaly_label"] = 1
    return result


def test_replay_alignment_artifact_binding_and_disposition(tmp_path: Path, signed_config) -> None:
    config, _, private, public_path = signed_config
    frame = telemetry()
    output = tmp_path / "run"
    result = run_replay(
        frame,
        config,
        output_directory=output,
        audit_private_key=private,
        dataset_id="synthetic-engineering-test",
        dataset_hash="a" * 64,
        dataset_license="TEST-ONLY",
        code_commit="b" * 40,
        sbom_hash="c" * 64,
    )
    assert result.risk_packets[0].timestamp == frame.iloc[120]["timestamp"].isoformat()
    assert result.manifest.split_boundaries["test"] == [120, 150]
    assert result.manifest.artifact_hash == file_sha256(output / "detector-artifact.joblib")
    assert all(
        packet.artifact_hash == result.manifest.artifact_hash for packet in result.risk_packets
    )
    assert all(record.disposition is Disposition.PENDING for record in result.recommendations)
    assert all(len(item.limitations) >= 3 for item in result.explanations)
    assert verify_audit(output / "audit.jsonl", load_public_key(public_path)) == 32

    schema_pairs = (
        ("risk-packets.jsonl", "risk-packet-v1.schema.json"),
        ("explanation-packets.jsonl", "explanation-packet-v1.schema.json"),
        ("recommendations.jsonl", "recommendation-record-v1.schema.json"),
    )
    for output_name, schema_name in schema_pairs:
        first = json.loads((output / output_name).read_text(encoding="utf-8").splitlines()[0])
        schema = json.loads(Path("schemas", schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(first)
    manifest_schema = json.loads(
        Path("schemas/run-manifest-v1.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(manifest_schema).validate(
        json.loads((output / "run-manifest.json").read_text(encoding="utf-8"))
    )

    target = next(
        record for record in result.recommendations if record.action is not Action.NOMINAL
    )
    updated = record_disposition(
        output,
        target.recommendation_id,
        Disposition.ACCEPTED,
        "operator@example.test",
        "OPERATOR_CONFIRMED",
        "Operator reviewed telemetry and accepted the advisory recommendation",
        private,
    )
    assert updated.disposition is Disposition.ACCEPTED
    assert verify_audit(output / "audit.jsonl", load_public_key(public_path)) == 33

    manifest_path = output / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["second_person_review_required"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    second_target = next(
        record
        for record in result.recommendations
        if record.action is not Action.NOMINAL
        and record.recommendation_id != target.recommendation_id
    )
    with pytest.raises(ValueError, match="second reviewer"):
        record_disposition(
            output,
            second_target.recommendation_id,
            Disposition.REJECTED,
            "operator@example.test",
            "FURTHER_REVIEW",
            "A second reviewer is required by the signed customer configuration",
            private,
        )


def test_missing_channel_forces_degraded_alert(tmp_path: Path, signed_config) -> None:
    config, _, private, _ = signed_config
    result = run_replay(
        telemetry().drop(columns=["voltage"]),
        config,
        output_directory=tmp_path / "degraded",
        audit_private_key=private,
        dataset_id="synthetic-engineering-test",
        dataset_hash="d" * 64,
        dataset_license="TEST-ONLY",
        code_commit="e" * 40,
        sbom_hash="f" * 64,
    )
    assert len(result.recommendations) == 1
    assert result.recommendations[0].action is Action.ALERT_ONLY
    assert result.risk_packets[0].system_mode is SystemMode.DEGRADED
    assert result.risk_packets[0].score is None


def test_nonempty_output_is_rejected_to_prevent_stale_evidence(
    tmp_path: Path, signed_config
) -> None:
    config, _, private, _ = signed_config
    output = tmp_path / "existing"
    output.mkdir()
    (output / "stale.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="stale evidence"):
        run_replay(
            telemetry(),
            config,
            output_directory=output,
            audit_private_key=private,
            dataset_id="test",
            dataset_hash="1" * 64,
            dataset_license="TEST",
            code_commit="2" * 40,
            sbom_hash="3" * 64,
        )
