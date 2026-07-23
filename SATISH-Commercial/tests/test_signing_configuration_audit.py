from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from conftest import config_mapping

from satish_commercial.audit import AuditLog, verify_audit
from satish_commercial.configuration import load_config, validate_unsigned_config
from satish_commercial.signing import load_public_key, sign_mapping


def test_config_signature_detects_tampering(tmp_path: Path, signing_material) -> None:
    private, public_path = signing_material
    signed = sign_mapping(config_mapping(), private)
    signed["risk_thresholds"]["critical"] = 999
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(signed), encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        load_config(path, public_path)


def test_signed_config_matches_public_schema(tmp_path: Path, signing_material) -> None:
    private, _ = signing_material
    signed = sign_mapping(config_mapping(), private)
    schema = json.loads(Path("schemas/config-pack-v1.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(signed)


def test_config_author_cannot_approve() -> None:
    mapping = config_mapping()
    mapping["independent_approver"] = mapping["author"]
    with pytest.raises(ValueError, match="cannot approve"):
        validate_unsigned_config(mapping)


def test_unknown_config_field_rejected() -> None:
    mapping = config_mapping()
    mapping["python_plugin"] = "unsafe.py"
    with pytest.raises(ValueError, match="unknown configuration fields"):
        validate_unsigned_config(mapping)


def test_audit_chain_detects_edit(tmp_path: Path, signing_material) -> None:
    private, public_path = signing_material
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, private)
    log.append("FIRST", {"value": 1})
    log.append("SECOND", {"value": 2})
    assert verify_audit(path, load_public_key(public_path)) == 2
    records = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(records[0])
    first["payload"]["value"] = 8
    records[0] = json.dumps(first)
    path.write_text("\n".join(records) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        verify_audit(path, load_public_key(public_path))
