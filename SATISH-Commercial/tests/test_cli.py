from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from conftest import config_mapping

from satish_commercial.audit import AuditLog
from satish_commercial.cli import main


def _telemetry(rows: int = 150) -> pd.DataFrame:
    rng = np.random.default_rng(91)
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="60s", tz="UTC"),
            "temperature": 20 + rng.normal(0, 0.2, rows),
            "voltage": 28 + rng.normal(0, 0.1, rows),
            "anomaly_label": np.zeros(rows, dtype=int),
            "mission_phase": "ROUTINE",
        }
    )
    frame.loc[132:136, "temperature"] = 45
    frame.loc[132:136, "anomaly_label"] = 1
    return frame


def test_cli_key_config_replay_audit_and_disposition(tmp_path: Path, capsys) -> None:
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    assert (
        main(
            [
                "keys",
                "generate",
                "--private-key",
                str(private_path),
                "--public-key",
                str(public_path),
            ]
        )
        == 0
    )

    unsigned_path = tmp_path / "config.json"
    unsigned_path.write_text(json.dumps(config_mapping()), encoding="utf-8")
    signed_path = tmp_path / "signed.json"
    assert (
        main(
            [
                "config",
                "sign",
                str(unsigned_path),
                "--private-key",
                str(private_path),
                "--output",
                str(signed_path),
            ]
        )
        == 0
    )
    assert main(["config", "verify", str(signed_path), "--public-key", str(public_path)]) == 0

    telemetry_path = tmp_path / "telemetry.csv"
    _telemetry().to_csv(telemetry_path, index=False)
    output = tmp_path / "run"
    assert (
        main(
            [
                "replay",
                str(telemetry_path),
                "--config",
                str(signed_path),
                "--public-key",
                str(public_path),
                "--audit-private-key",
                str(private_path),
                "--output",
                str(output),
                "--dataset-id",
                "synthetic-engineering-test",
                "--dataset-license",
                "TEST-ONLY",
            ]
        )
        == 0
    )
    assert (
        main(["audit", "verify", str(output / "audit.jsonl"), "--public-key", str(public_path)])
        == 0
    )

    recommendations = [
        json.loads(line)
        for line in (output / "recommendations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    target = next(item for item in recommendations if item["action"] != "NOMINAL")
    assert (
        main(
            [
                "recommendation",
                "dispose",
                str(output),
                target["recommendation_id"],
                "--disposition",
                "ACCEPTED",
                "--operator",
                "operator@example.test",
                "--reason-code",
                "OPERATOR_CONFIRMED",
                "--rationale",
                "Operator reviewed and accepted this advisory recommendation",
                "--audit-private-key",
                str(private_path),
            ]
        )
        == 0
    )
    assert "non_nominal_pending" in capsys.readouterr().out


def test_cli_release_gate_and_error_paths(tmp_path: Path, capsys) -> None:
    assert main(["release", "check", "release/release-record.example.yaml"]) == 2
    missing = tmp_path / "missing.pem"
    assert main(["config", "verify", "missing.json", "--public-key", str(missing)]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_audit_verify_uses_signature(tmp_path: Path, signing_material) -> None:
    private, public_path = signing_material
    audit = tmp_path / "audit.jsonl"
    AuditLog(audit, private).append("TEST", {"advisory_only": True})
    assert main(["audit", "verify", str(audit), "--public-key", str(public_path)]) == 0
