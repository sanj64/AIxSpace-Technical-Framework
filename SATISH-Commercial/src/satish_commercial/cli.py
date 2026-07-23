"""Offline command-line interface for signing, replay, audit, and release checks."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

import pandas as pd

from .audit import verify_audit
from .configuration import load_config, sign_config
from .contracts import Disposition, to_dict
from .pipeline import file_sha256, record_disposition, run_replay
from .release_gate import check_release_record
from .signing import generate_keypair, load_private_key, load_public_key


def _code_commit() -> str:
    try:
        git = shutil.which("git")
        if git is None:
            return "UNCOMMITTED"
        result = subprocess.run(  # noqa: S603  # nosec B603
            [git, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "UNCOMMITTED"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="satish", description="SATISH advisory-only historical replay console"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    keys = commands.add_parser("keys", help="manage offline Ed25519 keys")
    key_commands = keys.add_subparsers(dest="keys_command", required=True)
    generate = key_commands.add_parser("generate")
    generate.add_argument("--private-key", type=Path, required=True)
    generate.add_argument("--public-key", type=Path, required=True)

    config = commands.add_parser("config", help="sign or verify a governed config pack")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    sign = config_commands.add_parser("sign")
    sign.add_argument("source", type=Path)
    sign.add_argument("--private-key", type=Path, required=True)
    sign.add_argument("--output", type=Path, required=True)
    verify = config_commands.add_parser("verify")
    verify.add_argument("source", type=Path)
    verify.add_argument("--public-key", type=Path, required=True)

    replay = commands.add_parser("replay", help="run a replay-only paid evaluation")
    replay.add_argument("telemetry", type=Path)
    replay.add_argument("--config", type=Path, required=True)
    replay.add_argument("--public-key", type=Path, required=True)
    replay.add_argument("--audit-private-key", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--dataset-id", required=True)
    replay.add_argument("--dataset-license", required=True)
    replay.add_argument("--sbom", type=Path)

    audit = commands.add_parser("audit", help="verify the signed audit chain")
    audit_commands = audit.add_subparsers(dest="audit_command", required=True)
    audit_verify = audit_commands.add_parser("verify")
    audit_verify.add_argument("path", type=Path)
    audit_verify.add_argument("--public-key", type=Path, required=True)

    recommendation = commands.add_parser("recommendation", help="record human responsibility")
    recommendation_commands = recommendation.add_subparsers(
        dest="recommendation_command", required=True
    )
    disposition = recommendation_commands.add_parser("dispose")
    disposition.add_argument("run_directory", type=Path)
    disposition.add_argument("recommendation_id")
    disposition.add_argument(
        "--disposition", choices=["ACCEPTED", "REJECTED", "DEFERRED"], required=True
    )
    disposition.add_argument("--operator", required=True)
    disposition.add_argument("--reason-code", required=True)
    disposition.add_argument("--rationale", required=True)
    disposition.add_argument("--second-reviewer")
    disposition.add_argument("--require-second-reviewer", action="store_true")
    disposition.add_argument("--audit-private-key", type=Path, required=True)

    release = commands.add_parser("release", help="evaluate fail-closed sale/release gates")
    release_commands = release.add_subparsers(dest="release_command", required=True)
    release_check = release_commands.add_parser("check")
    release_check.add_argument("record", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "keys":
            generate_keypair(arguments.private_key, arguments.public_key)
            print(
                f"created private key {arguments.private_key} and public key {arguments.public_key}"
            )
            return 0
        if arguments.command == "config" and arguments.config_command == "sign":
            sign_config(arguments.source, arguments.private_key, arguments.output)
            print(f"signed configuration written to {arguments.output}")
            return 0
        if arguments.command == "config" and arguments.config_command == "verify":
            config = load_config(arguments.source, arguments.public_key)
            print(
                json.dumps(
                    {"valid": True, "pack_id": config.pack_id, "pack_hash": config.pack_hash}
                )
            )
            return 0
        if arguments.command == "replay":
            config = load_config(arguments.config, arguments.public_key)
            telemetry = pd.read_csv(arguments.telemetry)
            sbom_hash = (
                file_sha256(arguments.sbom) if arguments.sbom else "NOT_GENERATED-EVALUATION_ONLY"
            )
            replay_result = run_replay(
                telemetry,
                config,
                output_directory=arguments.output,
                audit_private_key=load_private_key(arguments.audit_private_key),
                dataset_id=arguments.dataset_id,
                dataset_hash=file_sha256(arguments.telemetry),
                dataset_license=arguments.dataset_license,
                code_commit=_code_commit(),
                sbom_hash=sbom_hash,
            )
            non_nominal = sum(
                item.action.value != "NOMINAL" for item in replay_result.recommendations
            )
            print(
                json.dumps(
                    {
                        "run_id": replay_result.manifest.run_id,
                        "output": str(replay_result.output_directory),
                        "non_nominal_pending": non_nominal,
                    }
                )
            )
            return 0
        if arguments.command == "audit":
            count = verify_audit(arguments.path, load_public_key(arguments.public_key))
            print(json.dumps({"valid": True, "records": count}))
            return 0
        if arguments.command == "recommendation":
            updated = record_disposition(
                arguments.run_directory,
                arguments.recommendation_id,
                Disposition(arguments.disposition),
                arguments.operator,
                arguments.reason_code,
                arguments.rationale,
                load_private_key(arguments.audit_private_key),
                second_reviewer_identity=arguments.second_reviewer,
                require_second_reviewer=arguments.require_second_reviewer,
            )
            print(json.dumps(to_dict(updated), sort_keys=True))
            return 0
        if arguments.command == "release":
            gate_results = check_release_record(arguments.record)
            for gate_result in gate_results:
                print(
                    json.dumps(
                        {
                            "gate": gate_result.name,
                            "approved": gate_result.approved,
                            "reasons": gate_result.reasons,
                        }
                    )
                )
            return 0 if all(item.approved for item in gate_results) else 2
    except Exception as exc:  # fail closed at the CLI boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
