from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import jsonschema

from satish_commercial.config_registry import ConfigRegistry, RegressionResult
from satish_commercial.release_gate import check_release_record


def test_json_schemas_are_valid() -> None:
    for path in Path("schemas").glob("*.schema.json"):
        jsonschema.Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_release_record_fails_closed() -> None:
    results = check_release_record(Path("release/release-record.example.yaml"))
    assert results
    assert not any(result.approved for result in results)


def test_config_activation_requires_regression_and_is_atomic(tmp_path: Path, signed_config) -> None:
    config, config_path, private, public_path = signed_config
    registry = ConfigRegistry(tmp_path / "registry", private)
    evidence_hash = hashlib.sha256(b"approved regression").hexdigest()
    activated = registry.activate(
        config_path,
        public_path,
        lambda pack: RegressionResult(True, evidence_hash, "all approved cases passed"),
    )
    assert activated.pack_hash == config.pack_hash
    pointer = json.loads(registry.current.read_text(encoding="utf-8"))
    assert pointer["pack_hash"] == config.pack_hash
    assert pointer["regression_evidence_hash"] == evidence_hash


def test_production_dependencies_exclude_research_models() -> None:
    project = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    for forbidden in ("tensorflow", "gymnasium", "stable-baselines3", "lstm", "ppo"):
        assert forbidden not in project


def test_commercial_package_has_no_command_transport_client() -> None:
    package_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("src/satish_commercial").glob("*.py")
    )
    forbidden_import = re.compile(
        r"^\s*(?:import|from)\s+(?:requests|socket|grpc|serial)(?:\s|\.|$)", re.MULTILINE
    )
    assert forbidden_import.search(package_text) is None
    for forbidden_symbol in ("send_command", "transmit_command", "actuator_client"):
        assert forbidden_symbol not in package_text
