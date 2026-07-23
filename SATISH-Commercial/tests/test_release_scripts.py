from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from scripts import create_checksums, generate_sbom, sign_bundle, verify_bundle


def test_signed_bundle_round_trip(tmp_path: Path, monkeypatch, signing_material) -> None:
    private, public_path = signing_material
    private_path = tmp_path / "private.pem"
    private_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    payload = bundle / "artifact.txt"
    payload.write_text("approved artifact\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["create_checksums", str(bundle)])
    assert create_checksums.main() == 0
    monkeypatch.setattr(
        sys, "argv", ["sign_bundle", str(bundle), "--private-key", str(private_path)]
    )
    assert sign_bundle.main() == 0
    monkeypatch.setattr(
        sys, "argv", ["verify_bundle", str(bundle), "--public-key", str(public_path)]
    )
    assert verify_bundle.main() == 0

    payload.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="checksum mismatch"):
        verify_bundle.main()


def test_sbom_is_generated_from_complete_lock(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "sbom.json"
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1784642400")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_sbom",
            "--requirements",
            "requirements.lock",
            "--output",
            str(output),
        ],
    )
    assert generate_sbom.main() == 0
    sbom = json.loads(output.read_text(encoding="utf-8"))
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert len(sbom["packages"]) == 50
    assert sbom["creationInfo"]["created"] == "2026-07-21T14:00:00Z"
